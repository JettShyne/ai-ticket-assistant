# -*- coding: utf-8 -*-
"""命令行版 V2：三层识别（规则 → 模型 → 同义词 → 转人工）。

用法：
    python main.py "我买的东西还没发货，想退款"     # 默认 auto：三层都用
    python main.py --rules "..."                  # 只跑关键词规则（V1 对照实验）
    python main.py --llm "..."                    # 规则 + 模型，禁用同义词（测模型真实能力）
    python main.py --check                        # 检查密钥是否配置好（不显示密钥内容）
    python main.py                                # 交互模式，输入 exit 退出
"""
import os
import sys

from engine import analyze

MODE_FLAGS = {"--rules": "rules", "--llm": "llm", "--auto": "auto"}


def check_env():
    """检查模型调用层是否就绪；只报「有没有配」，不打印密钥。"""
    try:
        import llm_classifier
    except Exception as exc:
        print("分类层导入失败：" + str(exc))
        return 1

    if llm_classifier.available():
        key = llm_classifier.api_key()
        print("模型调用层：可用")
        print("密钥：已读到（长度 {0}，内容不显示）".format(len(key)))
        print("模型：{0}".format(os.getenv("DEEPSEEK_MODEL", "deepseek-chat")))
        print("接口地址：{0}".format(os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")))
        return 0

    print("模型调用层：不可用")
    print("原因：没有读到 DEEPSEEK_API_KEY，或者没有安装 openai")
    print("做法：把项目里的 .env.example 复制成 .env，填上你的密钥，然后重跑本条命令")
    print("提示：没配密钥也能用，只是会自动跳过模型层，靠同义词兜底")
    return 1


def show(question, product="未知", order="", mode="auto"):
    result = analyze(question, product_type=product, order_info=order, mode=mode)
    print("=" * 60)
    print("客户问题　：" + question)
    print("分类　　　：" + result["category"] + "（规则 " + result["rule_id"] + "）")
    print("判定来源　：" + result["source"] + "（置信度 " + result["confidence"] + "）")
    print("判断过程　：" + result["reason"])
    print("是否转人工：" + ("是" if result["escalate"] else "否"))
    print("-" * 60)
    print("答复建议　：" + result["advice"])
    if result["basis"]:
        print("规则依据　：" + result["basis"])
    if result["need_info"]:
        print("待确认　　：" + "、".join(result["need_info"]))
    if result["follow_up"]:
        print("可先问客户：" + result["follow_up"][0])
    print("=" * 60)
    return result


def main():
    args = sys.argv[1:]
    mode = "auto"

    if args and args[0] in MODE_FLAGS:
        mode = MODE_FLAGS[args[0]]
        args = args[1:]

    if args and args[0] == "--check":
        return check_env()

    if args:
        show(" ".join(args), mode=mode)
        return 0

    print("AI 售后工单辅助台 · 命令行 V2（三模式：auto / llm / 同义词兜底，输入 exit 退出）")
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
        show(text, mode=mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
