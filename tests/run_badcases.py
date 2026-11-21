# -*- coding: utf-8 -*-
"""跑换说法用例，三种模式对比，并写入 BADCASES_RESULT.md。

用法（在项目根目录）：
    python tests/run_badcases.py                 # 默认 tests/badcases.json
    python tests/run_badcases.py real_cases.json # 换成真实客服用语

三种模式：
    rules  只用关键词规则（V1 行为）
    llm    规则优先 + 模型分类（禁同义词，用来测模型的真实能力）
    auto   规则 → 模型 → 同义词（产品默认行为）

判定口径（2026-11-21 调整，用户确认）：
- expect_action = "rule"     → 必须给出期望规则，才算「规则命中」
- expect_action = "escalate" → 必须转人工，才算「正确转人工」
- 该给规则却给了规则之外的结论 → 「错误答复」（最危险）
- 该转人工却套了一条规则       → 也算「错误答复」（可能让客服乱承诺）
- 该给规则、结果转人工         → 「未命中·安全转人工」（不算错，但没帮上忙）
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine import analyze  # noqa: E402

MODES = [("rules", "keywords only"), ("llm", "rules + model"), ("auto", "rules -> model -> synonyms")]


def load_cases(filename="badcases.json"):
    with open(os.path.join(HERE, filename), "r", encoding="utf-8") as fh:
        return json.load(fh)["cases"]


def judge(case, result):
    """返回 (类别, 说明)，类别取 rule_hit / escalate_ok / safe_miss / wrong。"""
    kind = case.get("expect_action", "rule")
    expect = case.get("expect", [])
    got_rule = result["rule_id"]
    escalated = bool(result["escalate"])

    if kind == "escalate":
        if escalated:
            return "escalate_ok", "正确转人工"
        return "wrong", "该转人工却给了结论（可能让客服乱承诺）"

    if got_rule in expect:
        return "rule_hit", "命中"
    if escalated:
        return "safe_miss", "未命中·安全转人工"
    return "wrong", "该给规则却给了别的结论"


def run_mode(cases, mode):
    rows = []
    for case in cases:
        result = analyze(case["text"], mode=mode)
        kind, note = judge(case, result)
        rows.append((case, result, kind, note))
    return rows


def main():
    filename = sys.argv[1] if len(sys.argv) > 1 else "badcases.json"
    cases = [case for case in load_cases(filename) if (case.get("text") or "").strip()]
    if not cases:
        print("没有可用用例：" + filename + " 里的 text 还是空的，先填真实说法再跑。")
        return 0

    print("=" * 78)
    print("换说法用例 · 三种模式对比（判定口径：规则命中 / 正确转人工 / 错误答复）")
    print("=" * 78)

    summary = {}
    tables = {}
    rule_total = sum(1 for case in cases if case.get("expect_action", "rule") == "rule")
    escalate_total = len(cases) - rule_total
    for mode, label in MODES:
        rows = run_mode(cases, mode)
        counts = {"rule_hit": 0, "escalate_ok": 0, "safe_miss": 0, "wrong": 0}
        for _, _, kind, _ in rows:
            counts[kind] += 1
        summary[mode] = counts
        tables[mode] = rows
        print("[{0}] {1}：规则命中 {2}/{3}｜正确转人工 {4}/{5}｜未命中·安全转人工 {6}｜错误答复 {7}".format(
            mode, label, counts["rule_hit"], rule_total, counts["escalate_ok"], escalate_total,
            counts["safe_miss"], counts["wrong"]))
        for case, result, kind, note in rows:
            print("   {0:<10} {1} 期望 {2} 实际 {3}（{4}）→ {5}".format(
                kind.upper(), case["id"],
                "/".join(case.get("expect") or ["转人工"]),
                result["rule_id"], result["source"], note))

    # ---- 写结果文件 ----
    lines = ["# 换说法用例结果（自动生成）", ""]
    lines.append("判定口径：expect_action=rule 必须给对规则；expect_action=escalate 必须转人工；"
                 "给错结论或该转人工却套规则，都算「错误答复」。")
    lines.append("")
    lines.append("| 模式 | 规则用例命中 | 转人工用例正确 | 未命中·安全转人工 | 错误答复 |")
    lines.append("|---|---|---|---|---|")
    for mode, label in MODES:
        counts = summary[mode]
        lines.append("| {0}（{1}） | {2}/{3} | {4}/{5} | {6} | {7} |".format(
            mode, label, counts["rule_hit"], rule_total, counts["escalate_ok"],
            escalate_total, counts["safe_miss"], counts["wrong"]))
    lines.append("")
    for mode, label in MODES:
        lines.append("## 模式 " + mode + " 明细")
        lines.append("")
        lines.append("| 用例 | 客户原话 | 期望 | 实际 | 判定来源 | 结果 |")
        lines.append("|---|---|---|---|---|---|")
        for case, result, kind, note in tables[mode]:
            expect_text = "/".join(case.get("expect") or ["转人工"])
            lines.append("| {0} | {1} | {2} | {3} | {4} | {5} |".format(
                case["id"], case["text"], expect_text, result["rule_id"],
                result["source"], note))
        lines.append("")
    lines.append("> 同义词表是按意图整理的，测试句也包含在其中，所以 auto 的命中率不能当作泛化能力证明。")
    lines.append("> N6「能不能便宜点」按产品判断应为「转人工、不承诺优惠」，不套用 R503 价保。")

    if filename == "badcases.json":
        out_name = "BADCASES_RESULT.md"
    else:
        out_name = "RESULT_" + filename.replace(".json", ".md")
    out = os.path.join(HERE, out_name)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("-" * 78)
    print("结果已写入：" + out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
