# -*- coding: utf-8 -*-
"""命令行版：读一句客户问题，输出答复建议。

用法：
    python main.py "客户说：我买的东西还没发货，想退款"
    python main.py            # 交互模式，输入 exit 退出
"""
import sys

from engine import analyze


def show(question, product="未知", order=""):
    result = analyze(question, product_type=product, order_info=order)
    print("=" * 60)
    print("客户问题：" + question)
    print("分类　　：" + result["category"] + "（规则 " + result["rule_id"] + "，置信度 " + result["confidence"] + "）")
    print("判断　　：" + result["reason"])
    print("是否转人工：" + ("是" if result["escalate"] else "否"))
    print("-" * 60)
    print("答复建议：" + result["advice"])
    if result["basis"]:
        print("规则依据：" + result["basis"])
    if result["need_info"]:
        print("待确认　：" + "、".join(result["need_info"]))
    print("=" * 60)


def main():
    if len(sys.argv) > 1:
        show(" ".join(sys.argv[1:]))
        return 0

    print("AI 售后工单辅助台 · 命令行版 V1（输入 exit 退出）")
    while True:
        try:
            text = input("\n客户问题> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if text.lower() in ("exit", "quit", "q"):
            break
        if text == "":
            continue
        show(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
