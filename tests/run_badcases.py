# -*- coding: utf-8 -*-
"""跑 6 条换说法用例，对比三种模式的命中率，并写入 BADCASES_RESULT.md。

用法（在项目根目录）：
    python tests/run_badcases.py

三种模式：
    rules  只用关键词规则（V1 行为）
    llm    规则优先 + 模型分类（禁同义词，用来测模型的真实能力）
    auto   规则 → 模型 → 同义词（产品默认行为）

「命中」= 输出规则 ID 在 expect 列表里。
注意：转人工不算错答，但在这里没命中就是没帮上忙，所以单独统计。
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


def run_mode(cases, mode):
    rows = []
    for case in cases:
        result = analyze(case["text"], mode=mode)
        hit = result["rule_id"] in case["expect"]
        wrong = (not hit) and (not result["escalate"])
        rows.append((case, result, hit, wrong))
    return rows


def main():
    filename = sys.argv[1] if len(sys.argv) > 1 else "badcases.json"
    cases = [case for case in load_cases(filename) if (case.get("text") or "").strip()]
    if not cases:
        print("没有可用用例：" + filename + " 里的 text 还是空的，先填真实说法再跑。")
        return 0
    print("=" * 78)
    print("换说法用例 · 三种模式对比")
    print("=" * 78)

    summary = {}
    tables = {}
    for mode, label in MODES:
        rows = run_mode(cases, mode)
        hits = sum(1 for _, _, hit, _ in rows if hit)
        wrongs = sum(1 for _, _, _, wrong in rows if wrong)
        summary[mode] = (hits, len(rows), wrongs)
        tables[mode] = rows
        print("[{0}] {1}：命中 {2}/{3}，错误答复 {4}".format(mode, label, hits, len(rows), wrongs))
        for case, result, hit, wrong in rows:
            mark = "HIT " if hit else ("WRONG" if wrong else "MISS")
            print("   {0} {1} 期望 {2} 实际 {3}（{4}·{5}）".format(
                mark, case["id"], "/".join(case["expect"]), result["rule_id"],
                result["source"], result["category"]))

    # ---- 写结果文件 ----
    lines = ["# 换说法用例结果（自动生成）", ""]
    lines.append("| 模式 | 命中 | 错误答复 | 有效命中率 |")
    lines.append("|---|---|---|---|")
    for mode, label in MODES:
        hits, total, wrongs = summary[mode]
        lines.append("| {0}（{1}） | {2}/{3} | {4} | {5:.0f}% |".format(
            mode, label, hits, total, wrongs, hits * 100.0 / total))
    lines.append("")
    for mode, label in MODES:
        lines.append("## 模式 " + mode + " 明细")
        lines.append("")
        lines.append("| 用例 | 客户原话 | 期望 | 实际 | 判定来源 | 结果 |")
        lines.append("|---|---|---|---|---|---|")
        for case, result, hit, wrong in tables[mode]:
            verdict = "命中" if hit else ("错误答复" if wrong else "未命中（转人工）")
            lines.append("| {0} | {1} | {2} | {3} | {4} | {5} |".format(
                case["id"], case["text"], "/".join(case["expect"]),
                result["rule_id"], result["source"], verdict))
        lines.append("")
    lines.append("> 判定口径：命中 = 规则 ID 落在期望集合内；错误答复 = 未命中且没有转人工。")
    lines.append("> 同义词表是按意图整理的，测试句也包含在其中，所以 auto 的命中率不能当作泛化能力证明。")

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
