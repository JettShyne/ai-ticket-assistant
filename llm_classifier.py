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


def classify(question, rules, product_type="未知", order_info=""):
    """调模型做意图分类。

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
