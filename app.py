# -*- coding: utf-8 -*-
"""AI 售后工单辅助台 V3-1：结构化分析（六个模块）。

运行方式：
    1) 双击 run.bat
    2) 或在 PyCharm 终端执行：python -m streamlit run app.py
"""
import streamlit as st

from analysis import build_report
from engine import RULES

st.set_page_config(page_title="AI 售后工单辅助台", page_icon="🎫", layout="centered")

st.title("AI 售后工单辅助台 · V3-1")
st.caption(
    "不只给一句答复：拆成「诉求 / 已知事实 / 信息缺口 / 争议点 / 建议与依据 / 不确定性」六块，"
    "并明确标出哪些信息没核实、哪些必须补。"
)

# ---------------- 侧边栏 ----------------
with st.sidebar:
    st.subheader("识别模式")
    mode_label = st.radio(
        "选择用哪一层识别客户诉求",
        [
            "auto（默认：规则 → 模型 → 同义词）",
            "rules（只跑关键词，V1 对照）",
            "llm（规则 + 模型，禁同义词）",
        ],
        index=0,
    )
    mode = mode_label.split("（")[0]
    st.caption("同一句话，在 rules 下可能判「转人工」，在 auto 下可能被模型或同义词认出。")
    st.divider()
    st.markdown("**模型层状态**")
    try:
        import llm_classifier

        if llm_classifier.available():
            st.success("已就绪（读到密钥）")
        else:
            st.warning("未配置密钥：模型层自动跳过，改用规则与同义词；事实抽取也不会执行")
    except Exception:
        st.warning("分类层导入失败：模型层不可用")

# ---------------- 一、输入 ----------------
st.subheader("一、客户问题")
customer_message = st.text_area(
    "客户原始消息 / 对话记录（必填）",
    placeholder="例如：我买的东西还没发货，我想退款",
    height=110,
)

st.subheader("二、业务信息（都可留空，留空会被标成「未提供」）")
col1, col2 = st.columns([1, 2])
with col1:
    product_type = st.selectbox(
        "商品类型",
        ["未知", "虚拟商品", "服装鞋包", "数码产品", "日用品", "其他"],
    )
with col2:
    order_info = st.text_input(
        "订单及交付情况",
        placeholder="例如：已签收两天 / 已发货未签收 / 已交付并使用",
    )

col_a, col_b = st.columns([1, 1])
with col_a:
    run = st.button("开始分析", type="primary", use_container_width=True)
with col_b:
    if st.button("清空", use_container_width=True):
        st.rerun()

# ---------------- 三、结果 ----------------
if run:
    st.subheader("三、分析结果")

    if not customer_message.strip():
        st.warning("请先填写客户原始消息。")
    else:
        report = build_report(
            customer_message,
            product_type=product_type,
            order_info=order_info,
            mode=mode,
        )
        problem = report["problem"]
        advice = report["advice"]

        if problem["escalate"]:
            st.error("**需要转人工** —— 这条不能让 AI 自己回。")
        elif report["conflicts"]:
            st.warning("**有矛盾信息** —— 先核实，别急着下结论。")
        else:
            st.success("**可以给出答复建议**（仍需客服确认后再发送）")

        # 一、问题类型与诉求
        st.markdown("### 一、问题类型与客户诉求")
        c1, c2, c3 = st.columns(3)
        c1.metric("问题类型", problem["type"])
        c2.metric("客户诉求", problem["demand"])
        c3.metric("命中规则", str(problem["rule_id"]))
        if problem["demand_quote"]:
            st.caption("诉求依据原话：「" + problem["demand_quote"] + "」")

        # 二、已知事实
        st.markdown("### 二、已知事实")
        st.caption("每条都标来源；「未核实」表示还没和订单后台核对过，本工具不连接电商后台。")
        rows = ["| 内容 | 来源 | 核实状态 |", "|---|---|---|"]
        for fact in report["known_facts"]:
            content = fact["content"].replace("|", "｜")
            rows.append("| {0} | {1} | {2} |".format(
                content, fact["source"], "已核实" if fact["verified"] else "未核实"))
        st.markdown("\n".join(rows))

        # 三、信息缺口
        st.markdown("### 三、信息缺口")
        if report["gaps"]["must"]:
            st.error("**必须核实：**" + "、".join(report["gaps"]["must"]))
        if report["gaps"]["optional"]:
            st.info("**可选补充：**" + "、".join(report["gaps"]["optional"]))
        if not report["gaps"]["must"] and not report["gaps"]["optional"]:
            st.write("规则未要求额外信息。")
        st.caption(report["gaps"]["note"])

        # 四、争议点
        st.markdown("### 四、争议点")
        if report["conflicts"]:
            for item in report["conflicts"]:
                st.warning("**{0} / {1}**：{2}\n\n处理：{3}".format(
                    item["client_says"], item["order_says"], item["note"], item["handle"]))
        else:
            st.write(report["conflicts_note"])

        # 五、处理建议与依据
        st.markdown("### 五、处理建议与依据")
        st.info(advice["text"])
        if advice["basis"]:
            st.markdown("**规则依据**")
            st.code(advice["basis"], language=None)
        else:
            st.warning("没有可引用的规则依据，不要向客户承诺具体处理结果。")
        st.caption("判定来源：{0}｜置信度：{1}".format(advice["source"], advice["confidence"]))

        # 六、不确定性与风险
        st.markdown("### 六、不确定性与风险")
        for item in report["uncertainty"]:
            st.markdown("- " + item)

        if report["follow_up"]:
            st.markdown("### 可先发给客户的澄清话术")
            st.code(report["follow_up"][0], language=None)

        with st.expander("产品边界（为什么它不什么都答）"):
            st.markdown(
                "1. **规则明确 + 信息齐全** → 给建议与依据；\n"
                "2. **关键信息缺失** → 标出缺什么，并区分必须核实 / 可选补充；\n"
                "3. **双方说法冲突** → 两边都摆出来，交人工核实，不替任何一方下结论；\n"
                "4. **赔付 / 投诉 / 例外承诺 / 规则未覆盖** → 转人工，AI 不独立担责。\n\n"
                "已知事实只来自你填的输入和模型抽取，每条都标了来源；不生成订单号、物流单号、凭证或金额。"
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
