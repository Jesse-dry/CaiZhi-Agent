# pages/4_Feynman_Evaluation.py
import streamlit as st
import time
from utils.state import init_session_state, go_to

init_session_state()

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

            # 保存评价结果供后续页面（如学习路径推荐）读取
            st.session_state["last_feynman_result"] = {
                "score": 82,
                "covered_points": ["快速冷却", "马氏体形成", "硬度提高"],
                "missing_points": ["碳原子扩散受限", "晶格畸变", "位错运动受阻"],
                "suggestion": "请补充说明马氏体为什么会阻碍位错运动，以及这如何导致硬度提高。"
            }
    else:
        st.warning("请先输入你的解释！")

# 评价结果出来后显示学习路径推荐按钮
if st.session_state.get("last_feynman_result"):
    st.divider()
    if st.button("生成个性化学习路径", type="primary"):
        st.session_state["demo_stage"] = "learning_path"
        go_to("learning_path")

# TODO: 替换为 services/feynman_service.py 的真实调用
# from services.feynman_service import evaluate
# result = evaluate(explanation=feynman_text, user_id=st.session_state.user_id)
