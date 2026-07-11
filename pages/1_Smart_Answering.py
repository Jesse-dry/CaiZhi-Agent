"""
页面 1：智能答疑（Smart Answering）
纯展示层 —— 所有业务逻辑在 services/qa_service.py

固定输出 7 个区块，不让大模型自由决定格式。
"""

import streamlit as st
from utils.state import init_session_state, go_to
from services.qa_service import answer_question

init_session_state()

st.title("💬 英文教材 RAG 智能答疑")
st.caption("💡 基于中英双语教材 + 知识图谱 + 术语表，试试输入：为什么淬火会提高钢的硬度？")

# ========== 渲染历史聊天记录（精简：只显示用户问题 + 简短回答） ==========
for message in st.session_state.qa_messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ========== 聊天输入框 ==========
if prompt := st.chat_input("请输入材料学专业问题..."):
    # 1. 显示用户消息
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.qa_messages.append({"role": "user", "content": prompt})

    # 2. 调用统一答疑服务
    with st.spinner("⏳ 正在检索中英双语教材与材料知识图谱..."):
        result = answer_question(prompt)

    # 3. 写入 session_state（指定 key 名）
    st.session_state["last_user_question"] = prompt
    st.session_state["last_answer"] = result
    st.session_state["last_qa_result"] = result
    st.session_state["current_knowledge_id"] = "K001"
    st.session_state["current_chain_id"] = result.get("chain_id", "C001")
    st.session_state["current_question_id"] = (
        result["self_test"]["question_id"]
        if result.get("self_test")
        else "Q001"
    )

    # 4. 固定 7 区块输出
    with st.chat_message("assistant"):
        # ---------- 区块 1：简明回答 ----------
        st.markdown("### 1. 简明回答")
        short = result.get("short_answer", "")
        st.markdown(short if short else "（暂无，待接入 LLM 后生成）")

        # ---------- 区块 2：材料学原理 ----------
        st.markdown("### 2. 材料学原理")
        principle = result.get("principle", "")
        st.markdown(principle if principle else "（暂无，待接入 LLM 后生成）")

        # ---------- 区块 3：因果链 ----------
        st.markdown("### 3. 因果链")
        causal_chain = result.get("causal_chain", [])
        if causal_chain:
            chain_str = " → ".join(f"**{label}**" for label in causal_chain)
            st.markdown(chain_str)
        else:
            st.markdown("（暂无匹配的因果链）")

        # ---------- 区块 4：中英文术语 ----------
        st.markdown("### 4. 中英文术语")
        key_terms = result.get("key_terms", [])
        if key_terms:
            cols = st.columns(min(len(key_terms), 5))
            for i, t in enumerate(key_terms):
                zh = t.get("zh", "")
                en = t.get("en", "")
                label = f"{zh} / {en}" if zh and en else (zh or en)
                with cols[i % len(cols)]:
                    st.info(label)
        else:
            st.markdown("（暂无匹配的术语）")

        # ---------- 区块 5：教材依据 ----------
        st.markdown("### 5. 教材依据")
        sources = result.get("sources", [])
        if sources:
            for s in sources[:5]:
                lang_flag = "🇨🇳" if s["language"] == "zh" else "🇺🇸"
                chapter_info = f" | {s['chapter']}" if s.get("chapter") else ""
                with st.expander(
                    f"{lang_flag} {s['file_name']}{chapter_info}（p.{s.get('page', '?')}）"
                ):
                    st.caption(s.get("text", ""))
        else:
            st.markdown("（暂无教材匹配结果）")

        # ---------- 区块 6：常见误区 ----------
        st.markdown("### 6. 常见误区")
        misconceptions = result.get("misconceptions", [])
        if misconceptions:
            for m in misconceptions:
                st.warning(f"⚠️ {m}")
        else:
            st.markdown("（暂无）")

        # ---------- 区块 7：自测题 ----------
        st.markdown("### 7. 自测题")
        self_test = result.get("self_test")
        if self_test:
            st.info(
                f"**{self_test['question']}**\n\n"
                f"编号：{self_test['question_id']} | 难度：{self_test.get('difficulty', '')}"
            )
        else:
            st.markdown("（暂无匹配的自测题）")

    # 5. 保存精简版聊天记录（只保存 short_answer，历史回显用）
    summary_for_history = result.get("short_answer", "") or "（回答已生成，见上方详情）"
    st.session_state.qa_messages.append({
        "role": "assistant",
        "content": summary_for_history,
    })

# ========== "开始自测" 按钮 ==========
if st.session_state.get("last_answer"):
    st.divider()
    if st.button("📝 开始自测", type="primary"):
        go_to("diagnosis")
