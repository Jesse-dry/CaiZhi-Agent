"""
页面 1：智能答疑（Smart Answering）
纯展示层 —— 所有业务逻辑在 services/qa_service.py

V2 (Phase 3)：使用 typed LearningSession 替代 st.session_state flat keys。
"""

import streamlit as st
from utils.state import init_session_state, get_session, save_session, go_to
from services.qa_service import answer_question
from schemas.qa import QAResult

init_session_state()

st.title("💬 英文教材 RAG 智能答疑")
st.caption("💡 基于中英双语教材 + 知识图谱 + 术语表，试试输入：为什么淬火会提高钢的硬度？")

# ========== 渲染历史聊天记录 ==========
for message in st.session_state.get("qa_messages", []):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ========== 聊天输入框 ==========
if prompt := st.chat_input("请输入材料学专业问题..."):
    # 1. 显示用户消息
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.setdefault("qa_messages", []).append({"role": "user", "content": prompt})

    # 2. 调用答疑服务
    with st.spinner("⏳ 正在检索中英双语教材与材料知识图谱..."):
        result_dict = answer_question(prompt)

    # 3. 写入 typed LearningSession
    session = get_session()
    session.qa_result = QAResult(**result_dict)
    session.knowledge_id = result_dict.get("knowledge_id", "K001")
    session.current_stage = "diagnosis"  # 推进到下一阶段
    session.current_knowledge_id = "K001"
    session.current_chain_id = result_dict.get("chain_id", "C001")
    session.current_question_id = (
        result_dict["recommended_question_id"]
        if result_dict.get("recommended_question_id")
        else "Q001"
    )
    save_session(session)

    # 同步扁平 key（过渡期 compat）
    st.session_state["last_user_question"] = prompt
    st.session_state["last_qa_result"] = result_dict
    st.session_state["last_answer"] = result_dict

    # 4. 渲染回答（V2: typed 访问优先，dict fallback）
    result = session.qa_result

    with st.chat_message("assistant"):
        # ---------- 区块 1：简明回答 ----------
        st.markdown("### 1. 简明回答")
        short = result.short_answer if result else ""
        st.markdown(short if short else "（暂无，待接入 LLM 后生成）")

        # ---------- 区块 2：材料学原理 ----------
        st.markdown("### 2. 材料学原理")
        principle = result.principle if result else ""
        st.markdown(principle if principle else "（暂无，待接入 LLM 后生成）")

        # ---------- 区块 3：因果链 ----------
        st.markdown("### 3. 因果链")
        causal_chain = result.causal_chain if result else []
        if causal_chain:
            chain_str = " → ".join(f"**{step.label_zh}**" for step in causal_chain)
            st.markdown(chain_str)
        else:
            st.markdown("（暂无匹配的因果链）")

        # ---------- 区块 4：中英文术语 ----------
        st.markdown("### 4. 中英文术语")
        key_terms = result.key_terms if result else []
        if key_terms:
            cols = st.columns(min(len(key_terms), 5))
            for i, t in enumerate(key_terms):
                label = f"{t.zh} / {t.en}" if t.zh and t.en else (t.zh or t.en)
                with cols[i % len(cols)]:
                    st.info(label)
        else:
            st.markdown("（暂无匹配的术语）")

        # ---------- 区块 5：教材依据 ----------
        st.markdown("### 5. 教材依据")
        sources = result.sources if result else []
        if sources:
            for s in sources[:5]:
                lang_flag = "🇨🇳" if s.language == "zh" else "🇺🇸"
                chapter_info = f" | {s.chapter}" if s.chapter else ""
                with st.expander(
                    f"{lang_flag} {s.file_name}{chapter_info}（p.{s.page_start or '?'}）"
                ):
                    st.caption(s.excerpt or s.text)
        else:
            st.markdown("（暂无教材匹配结果）")

        # ---------- 区块 6：常见误区 ----------
        st.markdown("### 6. 常见误区")
        misconceptions = result.misconceptions if result else []
        if misconceptions:
            for m in misconceptions:
                st.warning(f"⚠️ {m}")
        else:
            st.markdown("（暂无）")

        # ---------- 区块 7：自测题 ----------
        st.markdown("### 7. 自测题")
        if result and result.recommended_question_id:
            st.info(
                f"**推荐自测题**：{result.recommended_question_id}\n\n"
                f"难度：{result_dict.get('self_test', {}).get('difficulty', 'basic') if isinstance(result_dict, dict) else 'basic'}"
            )
        else:
            st.markdown("（暂无匹配的自测题）")

    # 5. 保存精简版聊天记录
    summary_for_history = (result.short_answer if result else "") or "（回答已生成，见上方详情）"
    st.session_state["qa_messages"].append({
        "role": "assistant",
        "content": summary_for_history,
    })

# ========== "开始自测" 按钮 ==========
session = get_session()
if session.qa_result:
    st.divider()
    if st.button("📝 开始自测", type="primary"):
        go_to("diagnosis")
