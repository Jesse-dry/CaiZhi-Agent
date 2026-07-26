"""
页面 3：苏格拉底式引导（Socratic Guidance）
学习闭环第 3 步：诊断误区 → 苏格拉底引导 → 费曼评价

V2 (Phase 3)：运行时状态移入 ui_input_cache["socratic"]；
业务结果写入 typed LearningSession。
"""

import streamlit as st
from utils.state import init_session_state, get_session, save_session, go_to
from services.socratic_service import (
    load_socratic_chain,
    get_step,
    get_total_steps,
    judge_answer_legacy as judge_answer,
    complete_socratic_legacy as complete_socratic,
)
from schemas.socratic import SocraticCompleteResult

init_session_state()

st.title("🦉 苏格拉底式引导")
st.caption("不直接给答案，通过层层追问引导你自己推导出结论。")

# ── 读取 session 中的 socratic_id ──
session = get_session()
socratic_id = session.current_socratic_id or "S001"
chain = load_socratic_chain(socratic_id)

if chain is None:
    st.error(f"未找到苏格拉底引导链：{socratic_id}")
    st.stop()

total_steps = get_total_steps(chain)

# ── 运行时状态：使用 ui_input_cache["socratic"] ──
cache = st.session_state.setdefault("ui_input_cache", {})
socratic_state = cache.setdefault("socratic", {
    "current_step": 1,
    "attempt_count": 0,
    "all_covered": [],
    "all_weak": [],
    "completed": False,
})

current_step_idx = socratic_state["current_step"]
attempt_count = socratic_state["attempt_count"]
all_covered = socratic_state["all_covered"]
all_weak = socratic_state["all_weak"]
completed = socratic_state["completed"]

# ── 进度条 ──
st.progress((current_step_idx - 1) / total_steps, f"步骤 {current_step_idx} / {total_steps}")
st.caption(f"📋 {chain.get('title', '')}")

# ── 渲染对话历史 ──
for msg in st.session_state.get("socratic_history", []):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ═══════════════════════════════════════
# 未完成：显示当前问题 + 接收回答
# ═══════════════════════════════════════
if not completed:
    current_step = get_step(chain, current_step_idx)

    if current_step is None:
        st.error(f"步骤 {current_step_idx} 不存在")
        st.stop()

    if attempt_count == 0:
        question_text = f"**第 {current_step_idx} 步**：{current_step.get('question', '')}"
        history = st.session_state.setdefault("socratic_history", [])
        if not history or history[-1]["content"] != question_text:
            with st.chat_message("assistant"):
                st.markdown(question_text)
            history.append({"role": "assistant", "content": question_text})

    if user_answer := st.chat_input("输入你的思考..."):
        with st.chat_message("user"):
            st.markdown(user_answer)
        st.session_state.setdefault("socratic_history", []).append({
            "role": "user", "content": user_answer,
        })

        socratic_state["attempt_count"] += 1
        result = judge_answer(
            step=current_step,
            student_answer=user_answer,
            attempt_count=socratic_state["attempt_count"],
        )

        for pt in result.get("covered_points", []):
            if pt not in socratic_state["all_covered"]:
                socratic_state["all_covered"].append(pt)
        for pt in result.get("missing_points", []):
            if pt not in socratic_state["all_weak"]:
                socratic_state["all_weak"].append(pt)

        with st.chat_message("assistant"):
            st.markdown(result["response"])
            quality = result.get("student_answer_quality", "")
            action = result.get("action", "")
            if action == "advance":
                st.caption(f"✅ 回答质量：{quality} | 推进到下一步")
            elif action == "simplify":
                st.caption(f"🔄 回答质量：{quality} | 简化重述")

        st.session_state["socratic_history"].append({
            "role": "assistant", "content": result["response"],
        })

        if action == "advance":
            if current_step_idx >= total_steps:
                socratic_state["completed"] = True
                final_result = complete_socratic(
                    socratic_id=socratic_id,
                    covered_points=socratic_state["all_covered"],
                    weak_points=socratic_state["all_weak"],
                )
                # 写入 typed LearningSession
                session = get_session()
                session.socratic_result = SocraticCompleteResult(**final_result)
                session.current_feynman_id = "F001"
                save_session(session)
                # 同步 flat key
                st.session_state["last_socratic_result"] = final_result
            else:
                socratic_state["current_step"] += 1
                socratic_state["attempt_count"] = 0

        st.rerun()

# ═══════════════════════════════════════
# 已完成：展示总结 + 导航
# ═══════════════════════════════════════
if completed:
    session = get_session()
    last_result = session.socratic_result

    st.success("🎉 苏格拉底引导完成！")

    with st.expander("📊 学习总结", expanded=True):
        if last_result:
            if last_result.summary:
                st.markdown(f"**核心结论**\n\n{last_result.summary}")
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("**已掌握知识点**")
                for pt in last_result.covered_points:
                    st.markdown(f"- ✅ {pt}")
            with col_b:
                st.markdown("**仍需加强**")
                for pt in last_result.remaining_weak_points:
                    st.markdown(f"- ⚠️ {pt}")

    st.divider()
    st.markdown("### 下一步")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🎤 进入费曼评价", type="primary", use_container_width=True):
            go_to("feynman")
    with col2:
        if st.button("🗺️ 生成学习路径", use_container_width=True):
            go_to("learning_path")

# ── 重置按钮 ──
if st.button("🔄 重新开始"):
    cache.pop("socratic", None)
    for key in ["socratic_history", "last_socratic_result"]:
        st.session_state.pop(key, None)
    st.rerun()
