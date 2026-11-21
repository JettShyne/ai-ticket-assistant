# -*- coding: utf-8 -*-
"""结构化分析验收测试（V3 第 1 步）。

验的不是「能不能跑」，而是六条产品底线：
1. 六个模块都要有，缺信息时也要能出结果（不许因为没填就崩）
2. 已知事实必须标来源，且不许出现输入里没有的内容（不编造订单/物流/凭证）
3. 缺信息要区分「必须核实」和「可选补充」
4. 只有两边说法都真实出现时才报争议；没争议就明说没有
5. 规则没覆盖时不许给结论、不许引用不存在的规则
6. 承诺类内容不许出现（不写金额、不保证退款）

用法：
    python tests/test_structured.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from analysis import build_report, format_report  # noqa: E402
import llm_classifier  # noqa: E402

CASES = [
    {
        "id": "S1",
        "name": "信息较完整：实物破损",
        "question": "收到的杯子碎了，拍了照片",
        "product": "日用品",
        "order": "已签收两天",
        "expect_rule": "R301",
        "expect_conflict": False,
    },
    {
        "id": "S2",
        "name": "信息缺失：只说东西坏了",
        "question": "东西坏了",
        "product": "未知",
        "order": "",
        "expect_rule": "R301",
        "expect_conflict": False,
    },
    {
        "id": "S3",
        "name": "双方说法冲突：客户说没发货，订单显示已签收",
        "question": "我买的东西还没发货，我想退款",
        "product": "服装鞋包",
        "order": "已签收",
        "expect_rule": "R101",
        "expect_conflict": True,
    },
    {
        "id": "S4",
        "name": "虚拟商品已使用",
        "question": "课程我已经看完了，现在想退款",
        "product": "虚拟商品",
        "order": "",
        "expect_rule": "R402",
        "expect_conflict": False,
    },
    {
        "id": "S5",
        "name": "规则未覆盖",
        "question": "你们公司周末上班吗",
        "product": "未知",
        "order": "",
        "expect_rule": "-",
        "expect_conflict": False,
    },
    {
        "id": "S6",
        "name": "赔付类：不许给承诺",
        "question": "你们这是假货，我要投诉，要求赔偿",
        "product": "日用品",
        "order": "",
        "expect_rule": "R000",
        "expect_conflict": False,
    },
]

FORBIDDEN_WORDS = ["已退款", "一定赔", "保证退", "承诺赔偿", "元给您", "已补发"]


def check(name, ok, detail=""):
    print(("[PASS] " if ok else "[FAIL] ") + name + (("  " + detail) if detail else ""))
    return ok


def facts_not_fabricated(report, question, product, order):
    """所有事实要么出自输入，要么被明确标成「未提供」。"""
    inputs = " ".join(x for x in [question, product, order] if x and x != "未知")
    for fact in report["known_facts"]:
        content = fact["content"]
        if fact["source"] == "缺失" or content.startswith("未提供："):
            continue
        if content.startswith("客户原话："):
            content = content[len("客户原话："):]
        elif content.startswith("商品类型："):
            content = content[len("商品类型："):]
        elif content.startswith("订单及交付情况："):
            content = content[len("订单及交付情况："):]
        if content not in inputs:
            return False, "事实不在输入里：" + fact["content"]
    return True, ""


def run_case(case):
    # 确定性用例强制关闭模型抽取：保证结果可复现、不花钱、不依赖当天模型状态。
    # 模型抽取单独在 fake_client_checks() 里验（要真跑就用 main.py 或 run_badcases.py）。
    report = build_report(case["question"], case["product"], case["order"], use_llm=False)
    results = []
    label = "{0} {1}".format(case["id"], case["name"])

    # 1. 六个模块齐全
    keys = ["problem", "known_facts", "gaps", "conflicts", "advice", "uncertainty"]
    results.append(check(label + " · 六个模块齐全", all(k in report for k in keys)))

    # 2. 分类结果正确
    results.append(check(
        label + " · 分类为 " + case["expect_rule"],
        report["problem"]["rule_id"] == case["expect_rule"],
        "实际 " + report["problem"]["rule_id"],
    ))

    # 3. 事实都有来源，且没有编造
    results.append(check(
        label + " · 每条事实都有来源",
        all(f.get("source") and f.get("verified") is False for f in report["known_facts"]),
    ))
    ok, detail = facts_not_fabricated(report, case["question"], case["product"], case["order"])
    results.append(check(label + " · 没有编造输入里没有的事实", ok, detail))

    # 4. 有诉求标签
    results.append(check(label + " · 给出客户诉求", bool(report["problem"]["demand"])))

    # 5. 争议判定
    has_conflict = bool(report["conflicts"])
    results.append(check(
        label + " · 争议判定符合预期",
        has_conflict == case["expect_conflict"],
        "有争议" if has_conflict else "无争议",
    ))
    if not has_conflict:
        results.append(check(label + " · 没争议时明说没有", "暂未发现明显争议" in report["conflicts_note"]))

    # 6. 不确定性与安全话术
    results.append(check(label + " · 给出了不确定性说明", len(report["uncertainty"]) > 0))
    blob = report["advice"]["text"] + " ".join(report["uncertainty"])
    hit = [word for word in FORBIDDEN_WORDS if word in blob]
    results.append(check(label + " · 没有承诺性表述", not hit, "命中：" + "、".join(hit) if hit else ""))

    return report, results


def extra_checks(reports):
    results = []

    # 缺信息场景：必须核实项不为空
    s2 = reports["S2"]
    results.append(check("S2 · 缺订单信息时给出必须核实项", len(s2["gaps"]["must"]) > 0,
                         "、".join(s2["gaps"]["must"])))
    results.append(check("S2 · 缺信息写进不确定性", any("关键信息" in item for item in s2["uncertainty"])))

    # 规则未覆盖：不许给结论
    s5 = reports["S5"]
    results.append(check("S5 · 规则未覆盖时不给结论", s5["problem"]["escalate"] is True))
    results.append(check("S5 · 未覆盖时说明没有依据可用", any("没有覆盖" in item for item in s5["uncertainty"]),
                         " | ".join(s5["uncertainty"])))
    results.append(check("S5 · 给出澄清话术", len(s5["follow_up"]) > 0))

    # 赔付类：必须转人工
    s6 = reports["S6"]
    results.append(check("S6 · 赔付类必须转人工", s6["problem"]["escalate"] is True))
    results.append(check("S6 · 诉求识别为赔偿/追责", s6["problem"]["demand"] == "赔偿 / 追责",
                         s6["problem"]["demand"]))

    # 冲突场景：冲突要写进不确定性
    s3 = reports["S3"]
    results.append(check("S3 · 冲突同时写进不确定性",
                         any("矛盾" in item for item in s3["uncertainty"])))
    results.append(check("S3 · 冲突处理不给任何一方下结论",
                         all("人工" in item["handle"] for item in s3["conflicts"])))

    # 客户已经提供证据时，不许再把它列成「缺」，更不许让客服重复索要
    s7 = build_report("东西坏了，我拍了照片", "日用品", "", use_llm=False)
    must = s7["gaps"]["must"]
    results.append(check("S7 · 客户已拍照则不再索要照片",
                         not any("照片" in item or "视频" in item for item in must),
                         "必须核实：" + "、".join(must)))
    results.append(check("S7 · 已提供的证据被单独标出", bool(s7["gaps"].get("covered")),
                         "、".join(s7["gaps"].get("covered", []))))
    results.append(check("S7 · 不确定性提醒先确认证据",
                         any("已表示提供" in item for item in s7["uncertainty"])))

    return results


def fake_client_checks():
    """模型抽取路径：有 key 时用抽取结果补事实，模型乱返回时必须回落。"""
    results = []

    class _Msg:
        def __init__(self, content):
            self.content = content

    class _Choice:
        def __init__(self, content):
            self.message = _Msg(content)

    class _Resp:
        def __init__(self, content):
            self.choices = [_Choice(content)]
            self.usage = type("U", (), {"total_tokens": 50})()

    class _Completions:
        def __init__(self, content):
            self._content = content

        def create(self, **kwargs):
            return _Resp(self._content)

    class _Client:
        def __init__(self, content):
            self.chat = type("C", (), {"completions": _Completions(content)})()

    def install(content):
        llm_classifier._ENV_LOADED = True
        llm_classifier._CLIENT = _Client(content)
        llm_classifier.available = lambda: True

    try:
        install('{"demand": "退款", "facts": [{"content": "客户说杯子碎了", "source": "客户陈述"}], "gaps": ["签收时间"]}')
        report = build_report("收到的杯子碎了，拍了照片", "日用品", "已签收两天")
        sources = [f["source"] for f in report["known_facts"]]
        results.append(check("模型抽取的事实被标为待核实", "模型抽取 · 待核实" in sources, str(sources)))
        results.append(check("模型抽取的缺口被并入可选补充", "签收时间" in report["gaps"]["optional"]))

        # 复述原话的抽取项应该被丢掉，否则「已知事实」里全是废话
        install('{"demand": "退款", "facts": [{"content": "收到的杯子碎了", "source": "客户陈述"}], "gaps": []}')
        report = build_report("收到的杯子碎了，拍了照片", "日用品", "")
        sources = [f["source"] for f in report["known_facts"]]
        results.append(check("复述原话的抽取项被丢掉", "模型抽取 · 待核实" not in sources, str(sources)))

        # 缺口与「未提供：商品类型」重复的，不再列第二遍
        install('{"demand": "退款", "facts": [], "gaps": ["商品类型", "订单信息"]}')
        report = build_report("东西坏了", "未知", "")
        optional = report["gaps"]["optional"]
        results.append(check("与「未提供」重复的缺口被去重",
                             "商品类型" not in optional and "订单信息" not in optional,
                             "、".join(optional)))

        install("这不是 JSON，我直接给个结论：赔 50 元。")
        report = build_report("收到的杯子碎了", "日用品", "")
        sources = [f["source"] for f in report["known_facts"]]
        results.append(check("模型输出垃圾时不追加任何事实", "模型抽取 · 待核实" not in sources))
        results.append(check("模型输出垃圾时报告仍完整", len(report["known_facts"]) > 0))
    finally:
        llm_classifier._ENV_LOADED = False
        llm_classifier._CLIENT = None
        import importlib

        importlib.reload(llm_classifier)

    return results


def main():
    all_results = []
    reports = {}

    print("=" * 78)
    print("结构化分析验收（V3 第 1 步）")
    print("=" * 78)

    for case in CASES:
        report, results = run_case(case)
        reports[case["id"]] = report
        all_results.extend(results)

    all_results.extend(extra_checks(reports))
    all_results.extend(fake_client_checks())

    print("-" * 78)
    print("样例输出（S3 冲突场景）")
    print("-" * 78)
    print(format_report(reports["S3"]))
    print("-" * 78)

    total = len(all_results)
    passed = sum(1 for item in all_results if item)
    print("通过 {0}/{1}".format(passed, total))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
