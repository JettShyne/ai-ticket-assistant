import streamlit as st

st.set_page_config(
    page_title="电商售后辅助工具",
    page_icon="🛠️",
    layout="wide"
)

st.title("电商售后问题分析与处理辅助工具")
st.caption("辅助客服整理售后信息、识别争议和判断下一步处理方向")

st.subheader("一、客户问题")

customer_message = st.text_area(
    "客户原始消息 / 对话记录（必填）",
    placeholder="请粘贴客户与客服之间的对话……",
    height=180
)

st.subheader("二、基础业务信息")

product_type = st.selectbox(
    "商品类型",
    ["未知", "虚拟商品", "服装鞋包", "数码产品", "日用品", "其他"]
)

product_info = st.text_input(
    "商品描述（选填）",
    placeholder="例如：某品牌蓝牙耳机"
)

order_info = st.text_area(
    "订单及交付情况（未知可填写未知）",
    placeholder="例如：订单已付款，商品已发货，物流显示已签收……",
    height=100
)

if st.button("开始分析", type="primary"):
    if not customer_message.strip():
        st.warning("请先填写客户原始消息。")
    else:
        st.subheader("三、分析结果")

        st.info("当前为页面测试版本，尚未接入大模型。")

        st.write("**客户原始消息：**")
        st.write(customer_message)

        st.write("**商品类型：**", product_type)
        st.write("**商品描述：**", product_info or "未提供")
        st.write("**订单及交付情况：**", order_info or "未知")

        st.success("页面交互正常，下一步将接入 AI 分析能力。")
