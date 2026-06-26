# pages/1_Smart Answering.py
import streamlit as st
import time

st.title("💬 英文教材 RAG 智能答疑")

st.caption("💡 尝试输入：为什么淬火会提高钢的硬度？")

# 初始化聊天历史记录
if "qa_messages" not in st.session_state:
    st.session_state.qa_messages = []

# 渲染历史聊天记录
for message in st.session_state.qa_messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 聊天输入框
if prompt := st.chat_input("请输入材料学专业问题..."):
    # 1. 渲染并保存用户输入
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.qa_messages.append({"role": "user", "content": prompt})

    # 2. 渲染助手回复状态，并加载假数据
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        # 模拟服务层调用和知识库检索的延迟
        message_placeholder.markdown("⏳ 正在检索英文教材与材料知识图谱...")
        time.sleep(1.5) 
        
        # 这里的排版严格按照架构文档中的输出结构建议
        mock_response = """
**【简明回答】**
淬火提高钢的硬度，主要是因为快速冷却抑制了碳原子的扩散，使奥氏体转变为碳过饱和的马氏体，从而引起强烈的晶格畸变，阻碍了位错运动。

**【英文术语依据】**
* Quenching (淬火)
* Martensite (马氏体)
* Lattice distortion (晶格畸变)
* Dislocation movement (位错运动)

**【图谱路径】**
`淬火` ➔ `快速冷却` ➔ `扩散受限` ➔ `形成马氏体` ➔ `晶格畸变` ➔ `位错运动受阻` ➔ `硬度提高`

**【自测题 & 下一步推荐】**
淬火强化与晶粒细化强化有什么本质区别？
👉 建议前往左侧 **“错题诊断”** 或 **“苏格拉底引导”** 模块继续深入学习。
        """
        # TODO: 替换为 services/qa_service.py 的真实调用
        # from services.qa_service import answer
        # mock_response = answer(prompt, user_id=st.session_state.user_id)

        # 展示最终结果
        message_placeholder.markdown(mock_response)
    
    # 3. 保存助手回复
    st.session_state.qa_messages.append({"role": "assistant", "content": mock_response})