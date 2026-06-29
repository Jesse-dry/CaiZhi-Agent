# pages/3_Socratic_Guidance.py
import streamlit as st
from utils.state import init_session_state, go_to

init_session_state()

st.title("🦉 苏格拉底式引导")

st.caption("💡 不直接给答案，通过层层追问引导你自己发现答案")

st.markdown("针对你的薄弱知识点：**淬火与硬度的关系**，我们将通过问答来一步步推导。")

socratic_id = st.session_state.get("current_socratic_id", "S001")

# 初始化第一句追问
if not st.session_state.socratic_history:
    st.session_state.socratic_history = [
        {"role": "assistant", "content": "让我们一步步来推导。首先：**淬火最大的工艺特点是什么？**"}
    ]

# 渲染对话历史
for msg in st.session_state.socratic_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 接收学生回复
if user_ans := st.chat_input("输入你的思考..."):
    # 展示学生发言
    with st.chat_message("user"):
        st.markdown(user_ans)
    st.session_state.socratic_history.append({"role": "user", "content": user_ans})

    # 根据对话步数给出对应追问（模拟 socratic.json 的递进链）
    step = sum(1 for m in st.session_state.socratic_history if m["role"] == "assistant")

    follow_ups = [
        "很好！接下来想一想：**冷却速度变快后，碳原子还有足够时间扩散吗？**",
        "对，碳原子来不及扩散。那么：**奥氏体会倾向于形成什么组织？**",
        "马氏体确实如此。进一步思考：**马氏体的晶格为什么容易发生畸变？**",
        "没错，碳过饱和是关键。那么：**晶格畸变会怎样影响位错运动？**",
        "最后一步：**位错运动受阻后，材料的硬度会怎样变化？**",
    ]

    if step <= len(follow_ups):
        next_q = follow_ups[step - 1]
        with st.chat_message("assistant"):
            st.markdown(next_q)
        st.session_state.socratic_history.append({"role": "assistant", "content": next_q})
    else:
        summary = "*(引导完成！总结：淬火通过快速冷却抑制碳原子扩散，使奥氏体转变为马氏体。马氏体中的碳原子过饱和，引起晶格畸变，阻碍位错运动，因此硬度提高。)*"
        with st.chat_message("assistant"):
            st.markdown(summary)
        st.session_state.socratic_history.append({"role": "assistant", "content": summary})

        st.session_state["last_socratic_summary"] = {
            "socratic_id": socratic_id,
            "completed": True,
            "summary": "淬火通过快速冷却抑制碳原子扩散，使奥氏体转变为马氏体；马氏体晶格畸变阻碍位错运动，因此硬度提高。"
        }
        st.session_state["current_feynman_id"] = "F001"

# 重置按钮
if st.button("🔄 重新开始"):
    st.session_state.socratic_history = [
        {"role": "assistant", "content": "让我们一步步来推导。首先：**淬火最大的工艺特点是什么？**"}
    ]
    st.rerun()

# 引导完成后显示进入费曼评价按钮
if st.session_state.get("last_socratic_summary"):
    st.divider()
    if st.button("进入费曼评价", type="primary"):
        st.session_state["demo_stage"] = "feynman"
        go_to("feynman")

# TODO: 替换为 services/socratic_service.py 的真实调用
# from services.socratic_service import next_question
# result = next_question(session_messages=st.session_state.socratic_history, user_id=st.session_state.user_id)
