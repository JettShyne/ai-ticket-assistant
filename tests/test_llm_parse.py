# -*- coding: utf-8 -*-
"""不花钱的分层测试：校验「模型调用层」的解析与失败回落是否正确。

模型本身要真调一次才能验证（需要 DEEPSEEK_API_KEY），这里用假的客户端
验证三件事：
1. 合法 JSON → 正确解析成 rule_id / escalate / missing；
2. 模型输出 ```json 包裹、或干脆不是 JSON → 解析失败返回 None；
3. 模型编造了不存在的规则 ID → 归为 UNKNOWN，绝不落到瞎编的规则上。

用法：
    python tests/test_llm_parse.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import llm_classifier  # noqa: E402
from engine import RULES, analyze  # noqa: E402


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeUsage:
    total_tokens = 100


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage()


class _FakeCompletions:
    def __init__(self, content):
        self._content = content

    def create(self, **kwargs):
        return _FakeResponse(self._content)


class _FakeChat:
    def __init__(self, content):
        self.completions = _FakeCompletions(content)


class _FakeClient:
    def __init__(self, content):
        self.chat = _FakeChat(content)


def with_fake_client(content):
    """让 llm_classifier 以为有 key，并把客户端换成假的。"""
    llm_classifier._ENV_LOADED = True
    llm_classifier._CLIENT = _FakeClient(content)
    llm_classifier.available = lambda: True


def restore():
    llm_classifier._ENV_LOADED = False
    llm_classifier._CLIENT = None
    import importlib

    importlib.reload(llm_classifier)


def check(name, ok, detail=""):
    print(("[PASS] " if ok else "[FAIL] ") + name + (("  " + detail) if detail else ""))
    return ok


def main():
    results = []

    # 1. 合法 JSON
    with_fake_client('{"rule_id": "R103", "escalate": false, "missing": ["签收时间"], "confidence": 0.82, "reason": "客户想退货退款"}')
    data = llm_classifier.classify("东西不满意，能退钱吗", RULES)
    results.append(check("合法 JSON 能解析", data is not None and data["rule_id"] == "R103", str(data)))
    results.append(check("置信度转成 0—1 小数", data is not None and 0.0 <= data["confidence"] <= 1.0))

    # 2. 代码块包裹
    with_fake_client('```json\n{"rule_id": "R202", "escalate": false, "missing": [], "confidence": 0.6, "reason": "物流未更新"}\n```')
    data = llm_classifier.classify("快递一直没动静", RULES)
    results.append(check("```json 包裹能解析", data is not None and data["rule_id"] == "R202"))

    # 3. 不是 JSON
    with_fake_client("我觉得应该退款给客户，可以退 50 元。")
    data = llm_classifier.classify("东西不满意", RULES)
    results.append(check("非 JSON 返回 None（触发回落）", data is None))

    # 4. 编造规则 ID
    with_fake_client('{"rule_id": "R999", "escalate": false, "missing": [], "confidence": 0.9, "reason": "编的"}')
    data = llm_classifier.classify("随便问一句", RULES)
    results.append(check("编造规则 ID 归为 UNKNOWN", data is not None and data["rule_id"] == "UNKNOWN", str(data)))

    # 5. 模型判 escalate
    with_fake_client('{"rule_id": "R000", "escalate": true, "missing": [], "confidence": 0.95, "reason": "要求赔偿"}')
    data = llm_classifier.classify("不退钱我就去投诉", RULES)
    results.append(check("escalate=true 能识别", data is not None and data["escalate"] is True))

    # 6. 端到端：模型给出 R202 → engine 用规则库的依据作答
    with_fake_client('{"rule_id": "R202", "escalate": false, "missing": ["快递单号"], "confidence": 0.8, "reason": "物流长时间未更新"}')
    result = analyze("快递一直没动静", mode="auto")
    ok = (result["rule_id"] == "R202" and result["source"] == "模型"
          and "R202-1" in result["basis"] and "快递单号" in result["need_info"])
    results.append(check("模型分类 → 规则库给依据", ok, result["rule_id"] + " / " + result["source"]))

    # 7. 模型失败 → 回落同义词，不空转
    with_fake_client("随便说点什么")
    result = analyze("能不能便宜点", mode="auto")
    ok = result["rule_id"] == "R503" and result["source"] == "同义词"
    results.append(check("模型失败 → 回落同义词", ok, result["rule_id"] + " / " + result["source"]))

    # 8. rules 模式不受模型与同义词影响
    with_fake_client('{"rule_id": "R103", "escalate": false, "missing": [], "confidence": 0.9, "reason": "x"}')
    result = analyze("东西不满意，能退钱吗", mode="rules")
    ok = result["rule_id"] == "-" and result["escalate"] is True
    results.append(check("rules 模式保持 V1 原样", ok, result["rule_id"] + " / " + result["category"]))

    restore()
    total = len(results)
    passed = sum(1 for item in results if item)
    print("-" * 60)
    print("通过 {0}/{1}".format(passed, total))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
