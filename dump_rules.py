# -*- coding: utf-8 -*-
"""从 engine.py 生成 rules.md，保证文档与代码一致。

运行：python dump_rules.py
"""
import os
from collections import OrderedDict

from engine import ESCALATE_KEYWORDS, RULES

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    groups = OrderedDict()
    for rule in RULES:
        groups.setdefault(rule["group"], []).append(rule)

    lines = []
    lines.append("# 售后规则库 V1（由 engine.py 自动生成，勿手改）\n")
    lines.append("- 规则总数：{0} 条".format(len(RULES)))
    lines.append("- 类别：{0} 类".format(len(groups)))
    lines.append("- 转人工触发词 {0} 个\n".format(len(ESCALATE_KEYWORDS)))

    lines.append("## 转人工优先规则（R000）\n")
    lines.append("命中任一触发词即转人工，且优先级高于所有业务规则：\n")
    lines.append("`" + "`、`".join(ESCALATE_KEYWORDS) + "`\n")
    lines.append("依据：R000-1 涉及赔偿与例外承诺必须人工授权；R000-2 投诉升级类问题不得由 AI 直接回复。\n")
    lines.append("规则未覆盖时（无任何业务规则命中）同样转人工：R000-3。\n")

    for group, items in groups.items():
        lines.append("## " + group + "\n")
        lines.append("| 规则 | 场景 | 触发词 | 需向客户确认 |")
        lines.append("|---|---|---|---|")
        for rule in items:
            lines.append("| {0} | {1} | {2} | {3} |".format(
                rule["id"],
                rule["category"].split(" · ")[-1],
                "、".join(rule["keywords"]),
                "、".join(rule["need_info"]) if rule["need_info"] else "—",
            ))
        lines.append("")
        for rule in items:
            lines.append("**" + rule["id"] + " · " + rule["category"] + "**")
            lines.append("- 建议：" + rule["advice"])
            lines.append("- 依据：" + rule["basis"])
            lines.append("")

    lines.append("---\n")
    lines.append("> 本规则库为模拟规则，用于个人项目演练与能力展示，不代表任何真实商家的售后制度。")

    out = os.path.join(HERE, "rules.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("已生成：" + out)


if __name__ == "__main__":
    main()
