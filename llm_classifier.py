# -*- coding: utf-8 -*-
"""意图分类层 V2：模型只判断「这句话属于哪条规则、缺什么信息」，不写答复。

为什么这样设计（见 tests/BADCASES.md）：
- 关键词匹配对换说法没有鲁棒性：6 句日常说法 0 命中；
- 但如果让模型直接写答复，它会编造规则、乱承诺、越权赔付；
- 所以把「理解客户说什么」交给模型，「能给什么依据」仍由 rules 库提供。
  模型输出必须落在既有规则 ID 上，落不上就返回 UNKNOWN。

失败策略：没有 key、超时、返回不是 JSON、规则 ID 不存在 → 一律返回 None，
由 engine 回落到关键词与同义词，绝不因为模型出错就给出没依据的答复。

密钥只从环境变量 / .env 读取，不写进代码、不进仓库。
"""
import json
import os
import re

DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"
TIMEOUT_SECONDS = 10.0
MAX_TOKENS = 220

_ENV_LOADED = False
_CLIENT = None


def load_env():
    """读 .env：先找当前目录，再找脚本所在目录（PyCharm / 双击 run.bat 都能用）。"""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    here = os.path.dirname(os.path.abspath(__file__))
    for folder in (os.getcwd(), here):
        path = os.path.join(folder, ".env")
        if os.path.isfile(path):
            load_dotenv(path, override=False)
            return
    load_dotenv(override=False)


def api_key():
    load_env()
    return (os.getenv("DEEPSEEK_API_KEY") or "").strip()


def available():
    """有没有可用的模型调用条件（有 key 且装了 openai）。"""
    if not api_key():
        return False
    try:
        import openai  # noqa: F401
    except Exception:
        return False
    return True


def _client():
    global _CLIENT
    if _CLIENT is None:
        from openai import OpenAI

        _CLIENT = OpenAI(
            api_key=api_key(),
            base_url=os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL),
            timeout=TIMEOUT_SECONDS,
            max_retries=0,
        )
    return _CLIENT


SYSTEM_PROMPT = """你是电商售后工单的意图分类器，只做分类，不写答复。

任务：读客户原话（可能口语、方言、错别字），判断它属于下面哪一条售后规则。

规则清单（只能用这些 ID）：
{table}

输出要求：
1. 只输出一个 JSON 对象，不要任何解释文字、不要 Markdown 代码块。
2. 字段：
   - "rule_id"：上面清单里的 ID；实在判断不出用 "UNKNOWN"。
   - "escalate"：true 表示涉及赔付、投诉、法律、媒体、例外承诺，必须人工处理。
   - "missing"：还需要向客户确认的信息，最多 3 条，每条不超过 12 字；没有就空数组。
   - "confidence"：0 到 1 之间的小数。
   - "reason"：一句话说明为什么选这条规则，不超过 30 字。
3. 禁止编造清单以外的规则 ID。
4. 禁止输出答复话术、禁止承诺赔偿金额、禁止给出处理结论。

示例：
客户："东西不满意，能退钱吗"
输出：{{"rule_id": "R103", "escalate": false, "missing": ["签收时间"], "confidence": 0.72, "reason": "客户想退货退款，属于签收后无理由退货"}}"""


def _rule_table(rules):
    lines = []
    for rule in rules:
        lines.append("- {0}：{1}".format(rule["id"], rule["category"]))
    return "\n".join(lines)


def _extract_json(text):
    """模型偶尔会包一层 ```json，这里做一次容错提取。"""
    if not text:
        return None
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None


def classify(question, rules, product_type="未知", order_info="", supplement=""):
    """调模型做意图分类。

    Args:
        supplement: 补充信息（单轮再分析时，客户或客服后来说的内容）。
    Returns:
        dict 或 None。成功时含 rule_id / escalate / missing / confidence / reason / usage。
        None 表示「不可用或不可信」，调用方必须回落。
    """
    if not available():
        return None
    question = (question or "").strip()
    if not question:
        return None

    user_parts = ["客户原话：" + question]
    if product_type and product_type != "未知":
        user_parts.append("商品类型：" + product_type)
    if order_info:
        user_parts.append("订单情况：" + order_info)
    if supplement:
        user_parts.append("补充信息（后来说的，优先参考）：" + supplement)

    try:
        resp = _client().chat.completions.create(
            model=os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL),
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT.format(table=_rule_table(rules)),
                },
                {"role": "user", "content": "\n".join(user_parts)},
            ],
            temperature=0,
            max_tokens=MAX_TOKENS,
            response_format={"type": "json_object"},
        )
    except Exception:
        return None

    content = resp.choices[0].message.content if resp.choices else ""
    data = _extract_json(content)
    if not isinstance(data, dict):
        return None

    rule_ids = {rule["id"] for rule in rules}
    rule_id = str(data.get("rule_id", "")).strip().upper()
    if rule_id not in rule_ids:
        rule_id = "UNKNOWN"

    missing = data.get("missing") or []
    if not isinstance(missing, list):
        missing = []
    missing = [str(item).strip()[:12] for item in missing if str(item).strip()][:3]

    try:
        confidence = float(data.get("confidence", 0.5))
    except Exception:
        confidence = 0.5
    confidence = min(max(confidence, 0.0), 1.0)

    usage = getattr(resp, "usage", None)
    return {
        "rule_id": rule_id,
        "escalate": bool(data.get("escalate", False)),
        "missing": missing,
        "confidence": confidence,
        "reason": str(data.get("reason", "")).strip()[:40],
        "tokens": getattr(usage, "total_tokens", 0) if usage else 0,
    }


EXTRACT_PROMPT = """你是售后工单的信息抽取器。只抽取，不判断责任，不给处理建议。
任务：从客户原话（可能还有商品类型、订单情况）里抽出三样东西：
1. 客户到底想要什么（诉求）；
2. 客户明确说了哪些事实；
3. 判断这件事还缺哪些信息。

只输出一个 JSON 对象，不要解释文字、不要 Markdown 代码块：
{
  "demand": "退款 / 补发 / 换货 / 开票 / 催件 / 要说法 / 未明确 之一",
  "facts": [{"content": "客户说了什么（不超过 30 字）", "source": "客户陈述"}],
  "gaps": ["还需要确认什么（每条不超过 12 字）"]
}

硬性规则：
- facts 只抽「具体细节」：时间、数量、规格、已做过的动作、客户提供的凭证、商品状态。
  不要重复整句概述，不要写「客户不满意」「客户想退款」这种原话复述。
- 客户只笼统抱怨、没给任何具体细节时，facts 返回空数组，这是正确行为。
- gaps 只列「判断售后需要、但对话里没有的客观信息」，例如订单状态、快递单号、签收时间、凭证、金额。
  不要列主观原因（如「不满意原因」）、不要列猜测。
- facts 只能来自给到的文字，禁止补充订单号、快递单号、金额、时间、凭证等原文没有的信息。
- 不做判断：不写「应该退款」「商家有责任」「客户在撒谎」。
- facts 最多 4 条，gaps 最多 4 条。"""


def extract(question, product_type="未知", order_info="", supplement=""):
    """从对话里抽取「诉求 / 已陈述事实 / 信息缺口」。

    Returns:
        dict 或 None。None 表示不可用或不可信，调用方必须回落，不得编造。
    """
    if not available():
        return None
    question = (question or "").strip()
    if not question:
        return None

    user_parts = ["客户原话：" + question]
    if product_type and product_type != "未知":
        user_parts.append("商品类型：" + product_type)
    if order_info:
        user_parts.append("订单情况：" + order_info)
    if supplement:
        user_parts.append("补充信息：" + supplement)

    try:
        resp = _client().chat.completions.create(
            model=os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL),
            messages=[
                {"role": "system", "content": EXTRACT_PROMPT},
                {"role": "user", "content": "\n".join(user_parts)},
            ],
            temperature=0,
            max_tokens=MAX_TOKENS,
            response_format={"type": "json_object"},
        )
    except Exception:
        return None

    content = resp.choices[0].message.content if resp.choices else ""
    data = _extract_json(content)
    if not isinstance(data, dict):
        return None

    facts = []
    for item in (data.get("facts") or [])[:4]:
        if not isinstance(item, dict):
            continue
        text = str(item.get("content", "")).strip()[:30]
        if text:
            facts.append({"content": text, "source": str(item.get("source", "客户陈述"))[:10]})

    gaps = []
    for item in (data.get("gaps") or [])[:4]:
        text = str(item).strip()[:12]
        if text:
            gaps.append(text)

    demand = str(data.get("demand", "")).strip()[:20]

    usage = getattr(resp, "usage", None)
    return {
        "demand": demand,
        "facts": facts,
        "gaps": gaps,
        "tokens": getattr(usage, "total_tokens", 0) if usage else 0,
    }


def _friendly_error(exc):
    """把常见报错翻译成人话，方便照着改。"""
    name = type(exc).__name__
    text = str(exc)
    lowered = text.lower()
    if "authentication" in lowered or "401" in lowered or "invalid api key" in lowered:
        return "密钥无效或写错了（401）：检查是不是复制少了字符，或密钥已被删除"
    if "402" in lowered or "insufficient" in lowered or "balance" in lowered:
        return "账户余额不足或没开通（402）：去 DeepSeek 控制台看下余额"
    if "404" in lowered or "model_not_found" in lowered or "does not exist" in lowered:
        return "模型名或接口地址不对（404）：检查 .env 里的 DEEPSEEK_MODEL 与 DEEPSEEK_BASE_URL"
    if "timeout" in lowered or "connection" in lowered or "network" in lowered:
        return "连不上接口（网络/超时）：检查网络、代理，或换一个接口地址"
    if "429" in lowered or "rate limit" in lowered:
        return "请求太频繁被限流（429）：等一分钟再试"
    return "{0}：{1}".format(name, text[:120])


def ping():
    """发一次极小的请求，验证「密钥能不能真的用起来」。

    Returns:
        (ok, message)。只花几个 token。
    """
    if not api_key():
        return False, "没有读到密钥"
    try:
        resp = _client().chat.completions.create(
            model=os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL),
            messages=[{"role": "user", "content": "只回复两个字母：ok"}],
            temperature=0,
            max_tokens=5,
        )
    except Exception as exc:
        return False, _friendly_error(exc)

    text = ""
    if resp.choices:
        text = (resp.choices[0].message.content or "").strip()[:20]
    usage = getattr(resp, "usage", None)
    tokens = getattr(usage, "total_tokens", 0) if usage else 0
    return True, "模型回了「{0}」，本次消耗 {1} tokens".format(text or "（空）", tokens)
