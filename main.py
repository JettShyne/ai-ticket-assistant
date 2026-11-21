# -*- coding: utf-8 -*-
"""命令行版 V3-1：结构化分析（六个模块）。

用法：
    python main.py "东西不满意，能退钱吗"          # 默认：结构化报告
    python main.py --brief "..."                  # 旧的一页式简版输出
    python main.py --rules "..."                  # 只跑关键词规则（V1 对照）
    python main.py --llm "..."                    # 规则 + 模型，禁同义词
    python main.py --check                        # 检查密钥是否配置好（不显示密钥内容）
    python main.py                                # 交互模式，输入 exit 退出
"""
import os
import shutil
import subprocess
import sys

from analysis import build_report, format_report
from engine import analyze

MODE_FLAGS = {"--rules": "rules", "--llm": "llm", "--auto": "auto"}


def open_env():
    """帮你把 .env 打开（没有就复制一份），省得找文件。"""
    here = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(here, ".env")
    example = os.path.join(here, ".env.example")

    if not os.path.isfile(env_path):
        if os.path.isfile(example):
            shutil.copyfile(example, env_path)
            print("项目里没有 .env，已从 .env.example 复制出一份。")
        else:
            with open(env_path, "w", encoding="utf-8") as fh:
                fh.write("DEEPSEEK_API_KEY=\n")
            print("项目里没有 .env，已新建一份。")

    print("正在用记事本打开：" + env_path)
    print("做两件事：")
    print("  1) 把密钥贴在 DEEPSEEK_API_KEY= 的等号后面（不加引号、不留空格）")
    print("  2) 按 Ctrl+S 保存，关掉记事本")
    print("然后跑：python main.py --check")
    try:
        subprocess.Popen(["notepad.exe", env_path])
    except Exception as exc:
        print("打不开记事本（" + str(exc) + "），请手动打开上面这个路径。")
        return 1
    return 0


def check_env():
    """三步体检：有没有装库、有没有读到密钥、密钥能不能真的用。

    只报「有没有配」和「通不通」，永远不打印密钥内容。
    """
    try:
        import llm_classifier
    except Exception as exc:
        print("模型层导入失败：" + str(exc))
        return 1

    print("第 1 步：检查依赖库")
    try:
        import openai  # noqa: F401
        import dotenv  # noqa: F401

        print("  [OK] openai 与 python-dotenv 都装了")
    except Exception as exc:
        print("  [缺] 没装依赖：" + str(exc))
        print("  做法：运行 python -m pip install -r requirements.txt")
        return 1

    print("第 2 步：检查密钥文件")
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not llm_classifier.api_key():
        print("  [缺] 没读到 DEEPSEEK_API_KEY")
        if os.path.isfile(env_path):
            print("  原因：.env 文件在，但等号后面是空的")
            print("  做法：跑 python main.py --open-env 打开它，")
            print("       把密钥贴在 DEEPSEEK_API_KEY= 后面（不加引号、不留空格），保存后重跑 --check")
        else:
            print("  原因：项目里没有 .env 文件")
            print("  做法：跑 python main.py --open-env，会自动复制一份并打开，贴密钥即可")
        return 1
    key = llm_classifier.api_key()
    print("  [OK] 读到了密钥（长度 {0}，内容不显示）".format(len(key)))
    if not key.startswith("sk-"):
        print("  [注意] DeepSeek 的密钥一般以 sk- 开头，检查一下是不是复制错了")

    print("第 3 步：真实调用一次（只花几个 token）")
    ok, message = llm_classifier.ping()
    if ok:
        print("  [OK] " + message)
        print("结论：模型调用层可用，可以直接跑 python main.py \"东西不满意，能退钱吗\"")
        return 0

    print("  [失败] " + message)
    print("  提示：密钥不通不影响其他功能，工具会自动跳过模型层，用规则与同义词兜底。")
    return 1


def show_structured(question, product="未知", order="", mode="auto"):
    report = build_report(question, product_type=product, order_info=order, mode=mode)
    print("=" * 66)
    print("客户问题：" + question)
    print("=" * 66)
    print(format_report(report))
    return report


def show_brief(question, product="未知", order="", mode="auto"):
    result = analyze(question, product_type=product, order_info=order, mode=mode)
    print("=" * 60)
    print("客户问题　：" + question)
    print("分类　　　：" + result["category"] + "（规则 " + result["rule_id"] + "）")
    print("判定来源　：" + result["source"] + "（置信度 " + result["confidence"] + "）")
    print("是否转人工：" + ("是" if result["escalate"] else "否"))
    print("-" * 60)
    print("答复建议　：" + result["advice"])
    if result["basis"]:
        print("规则依据　：" + result["basis"])
    if result["need_info"]:
        print("待确认　　：" + "、".join(result["need_info"]))
    print("=" * 60)
    return result


def main():
    args = sys.argv[1:]
    mode = "auto"
    brief = False

    while args and args[0].startswith("--"):
        flag = args[0]
        if flag in MODE_FLAGS:
            mode = MODE_FLAGS[flag]
        elif flag == "--brief":
            brief = True
        elif flag == "--check":
            return check_env()
        elif flag == "--open-env":
            return open_env()
        else:
            print("不认识的参数：" + flag)
            return 2
        args = args[1:]

    if args:
        if brief:
            show_brief(" ".join(args), mode=mode)
        else:
            show_structured(" ".join(args), mode=mode)
        return 0

    print("AI 售后工单辅助台 · 命令行 V3-1（结构化分析，输入 exit 退出）")
    print("提示：用 --rules 看 V1 原样，用 --brief 看简版输出")
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
        if brief:
            show_brief(text, mode=mode)
        else:
            show_structured(text, mode=mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
