# -*- coding: utf-8 -*-
"""跑 12 条测试用例，输出通过/失败表，并写入 RESULTS.md。

用法（在本目录下）：
    python tests/run_tests.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine import analyze  # noqa: E402


def load_cases():
    path = os.path.join(HERE, "cases.json")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)["cases"]


def run_one(case):
    result = analyze(
        case.get("text", ""),
        product_type=case.get("product", "未知"),
        order_info=case.get("order", ""),
    )
    expect_rule = case.get("expect_rule", "")
    expect_escalate = case.get("expect_escalate")
    ok = result["rule_id"] == expect_rule
    if expect_escalate is not None and result["escalate"] != expect_escalate:
        ok = False
    return result, ok


def main():
    cases = load_cases()
    rows = []
    for case in cases:
        result, ok = run_one(case)
        rows.append((case, result, ok))

    total = len(rows)
    passed = sum(1 for _, _, ok in rows if ok)

    print("=" * 78)
    print("AI 售后工单辅助台 · 12 条用例测试")
    print("=" * 78)
    for case, result, ok in rows:
        mark = "PASS" if ok else "FAIL"
        print("[{0}] {1} {2}".format(mark, case["id"], case["stage"]))
        print("     问题：" + case["text"])
        print("     期望：" + str(case.get("expect_rule")) + " | 实际：" + result["rule_id"] + " · " + result["category"])
        if not ok:
            print("     原因：" + result["reason"])
    print("-" * 78)
    print("通过 {0}/{1}".format(passed, total))

    # 写结果文件
    lines = []
    lines.append("# 测试结果（自动生成）\n")
    lines.append("- 用例总数：{0}".format(total))
    lines.append("- 通过：{0}".format(passed))
    lines.append("- 失败：{0}\n".format(total - passed))
    lines.append("| 用例 | 阶段 | 客户问题 | 期望规则 | 实际规则 | 结果 |")
    lines.append("|---|---|---|---|---|---|")
    for case, result, ok in rows:
        lines.append("| {0} | {1} | {2} | {3} | {4} | {5} |".format(
            case["id"], case["stage"], case["text"],
            case.get("expect_rule"), result["rule_id"], "通过" if ok else "失败"))
    lines.append("")
    lines.append("> 规则为模拟规则，用于演练与能力展示，不代表任何真实商家的售后制度。")

    out = os.path.join(HERE, "RESULTS.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("结果已写入：" + out)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
