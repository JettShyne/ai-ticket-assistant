# -*- coding: utf-8 -*-
"""AI 售后工单辅助台 V1：规则版页面（暂未接入大模型）。

运行方式：
    1) 双击 run.bat
    2) 或在 PyCharm 终端执行：python -m streamlit run app.py
"""
import streamlit as st

from engine import RULES, analyze

st.set_page_config(page_title="AI 售后工单辅助台", page_icon="🎫", layout="centered")

st.title("AI 售后工单辅助台 · V1")
st.caption("规则版演示：不调用模型，只做规则匹配与边界判断，用于验证「AI 该答什么、不该答什么」。")

# ---------------- 一、客户问题 ----------------
st.subheader("一、客户问题")
customer_message = st.text_area(
    "客户原始消息 / 对话记录（必填）",
    placeholder="例如：我买的东西还没发货，想退款",
    height=120,
)

# ---------------- 二、基础业务信息 ----------------
st.subheader("二、基础业务信息")
col1, col2 = st.columns([1, 2])
with col1:
    product_type = st.selectbox(
        "商品类型",
        ["未知", "虚拟商品", "服装鞋包", "数码产品", "日用品", "其他"],
    )
with col2:
    order_info = st.text_input(
        "订单及交付情况（选填）",
        placeholder="例如：已签收三天 / 已发货未签收 / 已交付并使用",
    )

col_a, col_b = st.columns([1, 1])
with col_a:
    run = st.button("开始分析", type="primary", use_container_width=True)
with col_b:
    if st.button("清空", use_container_width=True):
        st.rerun()

# ---------------- 三、分析结果 ----------------
if run:
    st.subheader("三、分析结果")

    if not customer_message.strip():
        st.warning("请先填写客户原始消息。")
    else:
        result = analyze(customer_message, product_type=product_type, order_info=order_info)

        if result["escalate"]:
            st.error("**需要转人工** —— 这条不能让 AI 自己回。")
        else:
            st.success("**可以给出答复建议**（仍需客服确认后再发送）")

        left, right, third = st.columns(3)
        with left:
            st.markdown("**问题分类**")
            st.write(result["category"])
        with right:
            st.markdown("**命中规则**")
            st.write(result["rule_id"])
        with third:
            st.markdown("**置信度**")
            st.write(result["confidence"])

        st.markdown("**判断依据**")
        st.write(result["reason"])

        st.markdown("**答复建议**")
        st.info(result["advice"])

        if result["basis"]:
            st.markdown("**规则依据**")
            st.code(result["basis"], language=None)

        if result["need_info"]:
            st.markdown("**还需要向客户确认**")
            for item in result["need_info"]:
                st.markdown("- " + item)

        with st.expander("为什么不是「什么都答」（产品边界说明）"):
            st.markdown(
                "本版把输出分成三类：\n"
                "1. **规则明确 + 信息齐全** → 给答复建议与规则依据；\n"
                "2. **关键信息缺失** → 提示补充，不硬答；\n"
                "3. **赔付 / 投诉 / 例外承诺 / 规则未覆盖** → 转人工，AI 不独立担责。"
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
