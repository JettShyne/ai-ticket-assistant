# -*- coding: utf-8 -*-
"""AI 售后工单辅助台 V3-2：结构化分析（六模块）+ 单轮补充信息再分析。

运行方式：
    1) 双击 run.bat
    2) 或在终端执行：python -m streamlit run app.py
"""
import streamlit as st

from analysis import build_report
from engine import RULES

st.set_page_config(page_title="AI 售后工单辅助台", page_icon="🎫", layout="centered")

st.title("AI 售后工单辅助台")
st.caption("一句话 → 六块结构化判断：诉求 / 已知事实 / 信息缺口 / 争议点 / 建议与依据 / 不确定性")

# ---------------- 侧边栏 ----------------
with st.sidebar:
    st.subheader("识别模式")
    mode_label = st.radio(
        "选择用哪一层识别客户诉求",
        ["auto（默认：规则 → 模型 → 同义词）", "rules（只跑关键词）", "llm（规则 + 模型，禁同义词）"],
        index=0,
    )
    mode = mode_label.split("（")[0]
    st.divider()
    st.markdown("**模型层状态**")
    try:
        import llm_classifier

        if llm_classifier.available():
            st.success("已就绪（读到密钥）")
        else:
            st.warning("未配置密钥：自动跳过模型层，改用规则与同义词兜底")
    except Exception:
        st.warning("模型层不可用：改用规则与同义词兜底")

# ================= 输入 =================
st.header("输入")

customer_message = st.text_area(
    "客户原话（必填）",
    placeholder="例如：东西坏了，我拍了照片",
    height=90,
)

col1, col2 = st.columns([1, 2])
with col1:
    product_type = st.selectbox("商品类型", ["未知", "虚拟商品", "服装鞋包", "数码产品", "日用品", "其他"])
with col2:
    order_info = st.text_input("订单及交付情况（可留空）", placeholder="例如：已签收两天 / 已发货未签收")

supplement = st.text_area(
    "补充信息（可留空；填了会重新分析一次）",
    placeholder="例如：1号签收的，照片已经发你们客服了",
    height=68,
)

col_a, col_b = st.columns([1, 1])
with col_a:
    run = st.button("开始分析", type="primary", use_container_width=True)
with col_b:
    if st.button("清空", use_container_width=True):
        st.rerun()

# ================= 结果 =================
if run:
    st.header("分析结果")

    if not customer_message.strip():
        st.warning("请先填写客户原话。")
    else:
        report = build_report(
            customer_message,
            product_type=product_type,
            order_info=order_info,
            mode=mode,
            supplement=supplement,
        )
        problem = report["problem"]
        advice = report["advice"]

        if problem["escalate"]:
            st.error("需要转人工 —— 这条不能让 AI 自己回。")
        elif report["conflicts"]:
            st.warning("有矛盾信息 —— 先核实，别急着下结论。")
        else:
            st.success("可以给出答复建议（仍需客服确认后再发送）。")

        # 1 · 问题类型与客户诉求
        st.subheader("1. 问题类型与客户诉求")
        c1, c2, c3 = st.columns(3)
        c1.metric("问题类型", problem["type"])
        c2.metric("客户诉求", problem["demand"])
        c3.metric("命中规则", str(problem["rule_id"]))
        if problem["demand_quote"]:
            st.caption("诉求依据原话：「" + problem["demand_quote"] + "」")

        # 2 · 已知事实
        st.subheader("2. 已知事实")
        rows = ["| 内容 | 来源 | 核实状态 |", "|---|---|---|"]
        for fact in report["known_facts"]:
            content = fact["content"].replace("|", "｜")
            rows.append("| {0} | {1} | {2} |".format(
                content, fact["source"], "已核实" if fact["verified"] else "未核实"))
        st.markdown("\n".join(rows))
        st.caption("每条都标来源；「未核实」= 还没和订单后台核对过（本工具不连接电商后台）。")

        # 3 · 信息缺口
        st.subheader("3. 信息缺口")
        if report["gaps"]["must"]:
            st.error("必须核实：" + "、".join(report["gaps"]["must"]))
        if report["gaps"]["optional"]:
            st.info("可选补充：" + "、".join(report["gaps"]["optional"]))
        if report["gaps"].get("covered"):
            st.success("客户已提供：" + "、".join(report["gaps"]["covered"]) + "（先确认收到，不要再索要）")
        if report["gaps"].get("filled"):
            st.success("本次补充已补齐：" + "、".join(report["gaps"]["filled"]))
        if not any([report["gaps"]["must"], report["gaps"]["optional"],
                    report["gaps"].get("covered"), report["gaps"].get("filled")]):
            st.write("规则未要求额外信息。")

        # 4 · 争议点
        st.subheader("4. 争议点")
        if report["conflicts"]:
            for item in report["conflicts"]:
                st.warning("{0} / {1}：{2}\n\n处理：{3}".format(
                    item["client_says"], item["order_says"], item["note"], item["handle"]))
        else:
            st.write(report["conflicts_note"])

        # 5 · 处理建议与依据
        st.subheader("5. 处理建议与依据")
        st.info(advice["text"])
        if advice.get("note"):
            st.warning(advice["note"])
        if advice["basis"]:
            st.code(advice["basis"], language=None)
        else:
            st.warning("没有可引用的规则依据，不要向客户承诺具体处理结果。")
        st.caption("判定来源：{0}｜置信度：{1}".format(advice["source"], advice["confidence"]))

        # 6 · 不确定性与风险
        st.subheader("6. 不确定性与风险")
        for item in report["uncertainty"]:
            st.markdown("- " + item)

        # 这次补充改变了什么
        if report.get("changes"):
            st.subheader("这次补充改变了什么")
            for item in report["changes"]:
                st.markdown("- " + item)

        if report["follow_up"]:
            st.markdown("**可以先发给客户的澄清话术**")
            st.code(report["follow_up"][0], language=None)

        with st.expander("产品边界：为什么它不什么都答"):
            st.markdown(
                "1. **规则明确 + 信息齐全** → 给建议与依据；\n"
                "2. **关键信息缺失** → 标出缺什么，分「必须核实 / 可选补充」；\n"
                "3. **双方说法冲突** → 两边都摆出来，交人工核实；\n"
                "4. **赔付 / 投诉 / 例外承诺 / 规则未覆盖** → 转人工，AI 不独立担责。\n\n"
                "已知事实只来自你填的输入和模型抽取，不生成订单号、物流单号、凭证或金额。"
            )

st.divider()
with st.expander("查看规则库（共 " + str(len(RULES)) + " 条，5 类）"):
    current_group = None
    for rule in RULES:
        if rule["group"] != current_group:
            current_group = rule["group"]
            st.markdown("### " + current_group)
        st.markdown("**" + rule["id"] + " · " + rule["category"] + "**")
        st.markdown("触发词：" + "、".join(rule["keywords"]))
        st.markdown("依据：" + rule["basis"])
        st.markdown("---")

st.caption("规则为模拟规则，用于演练与能力展示，不代表任何真实商家的售后制度；输出不对外承诺。")
