# -*- coding: utf-8 -*-
"""页面冒烟测试：用 Streamlit 官方 AppTest 真跑一遍 app.py，确认能出结果。

不需要打开浏览器，也不需要密钥（没密钥时页面会自动走同义词兜底）。

用法：
    python tests/test_app_smoke.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from streamlit.testing.v1 import AppTest  # noqa: E402


def check(name, ok, detail=""):
    print(("[PASS] " if ok else "[FAIL] ") + name + (("  " + detail) if detail else ""))
    return ok


def main():
    results = []

    # 1. 首次渲染
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60)
    at.run()
    results.append(check("页面首次渲染无异常", not at.exception, str(at.exception)[:200] if at.exception else ""))

    # 2. 输入一句换说法，点「开始分析」
    at.text_area[0].input("东西不满意，能退钱吗")
    at.button[0].click()
    at.run()
    results.append(check("点击分析后无异常", not at.exception, str(at.exception)[:200] if at.exception else ""))

    texts = []
    for element in (list(at.markdown) + list(at.success) + list(at.error) + list(at.info)
                    + list(at.code) + list(at.caption) + list(at.warning)):
        value = getattr(element, "value", "")
        if value:
            texts.append(str(value))
    blob = " ".join(texts)

    results.append(check("结果里出现规则 R103", "R103" in blob))
    results.append(check("结果里标明判定来源", "判定来源" in blob))
    results.append(check("六个模块都在", all(
        title in blob for title in ["问题类型与客户诉求", "已知事实", "信息缺口", "争议点", "处理建议与依据", "不确定性与风险"])))
    results.append(check("已知事实标了来源", "客户陈述" in blob))
    results.append(check("没有抛错提示", len(at.exception) == 0))

    # 3. 空输入时给出提示，而不是崩
    at2 = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run()
    at2.text_area[0].input("   ")
    at2.button[0].click()
    at2.run()
    results.append(check("空输入不崩、给 warning", (not at2.exception) and len(at2.warning) > 0))

    total = len(results)
    passed = sum(1 for item in results if item)
    print("-" * 60)
    print("通过 {0}/{1}".format(passed, total))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
