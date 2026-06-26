# pages/4_Feynman's evaluation.py
import streamlit as st
import time

st.title("🗣️ 费曼学习法评价")

st.caption("💡 用你自己的话把概念讲清楚——AI 从五个维度评价你是否真正理解")

st.markdown("### 🎯 挑战：向同学解释为什么淬火会提高硬度")

# 多行文本输入框
feynman_text = st.text_area("请用你自己的话解释：", height=150)

# 提交按钮
if st.button("提交评价"):
    if feynman_text:
        # 模拟 AI 评分延迟
        with st.spinner("AI 正在根据概念、因果链和术语进行多维度评分..."):
            time.sleep(1.5)

            st.markdown("### 📊 评价结果")
            st.markdown("""
            **总得分：82 / 100**

            ✅ **讲清楚的部分**：你讲清楚了快速冷却和马氏体形成。
            ❌ **缺失的部分**：还没有讲清楚无扩散相变和晶格畸变。

            **详细维度打分（参考）**：
            * 概念准确性：25 / 30
            * 因果链完整性：20 / 30
            * 术语规范性：12 / 15
            * 应用迁移能力：15 / 15
            * 表达清晰度：10 / 10
            """)
    else:
        st.warning("请先输入你的解释！")

# TODO: 替换为 services/feynman_service.py 的真实调用
# from services.feynman_service import evaluate
# result = evaluate(explanation=feynman_text, user_id=st.session_state.user_id)
