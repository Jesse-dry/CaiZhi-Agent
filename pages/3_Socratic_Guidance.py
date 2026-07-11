"""
页面 3：苏格拉底式引导（Socratic Guidance）
学习闭环第 3 步：诊断误区 → 苏格拉底引导 → 费曼评价

预定义教学台阶 + 关键词匹配判断回答质量 → 推进/提示/重问。
"""

import streamlit as st
from utils.state import init_session_state, go_to
from services.socratic_service import (
    load_socratic_chain,
    get_step,
    get_total_steps,
    judge_answer,
    complete_socratic,
)

init_session_state()

st.title("🦉 苏格拉底式引导")
st.caption("不直接给答案，通过层层追问引导你自己推导出结论。")

# ── 读取上一页传递的 socratic_id ──
socratic_id = st.session_state.get("current_socratic_id", "S001")
chain = load_socratic_chain(socratic_id)

if chain is None:
    st.error(f"未找到苏格拉底引导链：{socratic_id}")
    st.stop()

total_steps = get_total_steps(chain)

# ── 初始化状态 ──
if "socratic_current_step" not in st.session_state:
    st.session_state["socratic_current_step"] = 1
if "socratic_attempt_count" not in st.session_state:
    st.session_state["socratic_attempt_count"] = 0
if "socratic_all_covered" not in st.session_state:
    st.session_state["socratic_all_covered"] = []
if "socratic_all_weak" not in st.session_state:
    st.session_state["socratic_all_weak"] = []
if "socratic_completed" not in st.session_state:
    st.session_state["socratic_completed"] = False

# ── 快捷变量 ──
current_step_idx = st.session_state["socratic_current_step"]
attempt_count = st.session_state["socratic_attempt_count"]
all_covered = st.session_state["socratic_all_covered"]
all_weak = st.session_state["socratic_all_weak"]
completed = st.session_state["socratic_completed"]

# ── 进度条 ──
st.progress((current_step_idx - 1) / total_steps, f"步骤 {current_step_idx} / {total_steps}")
st.caption(f"📋 {chain.get('title', '')}")

# ═══════════════════════════════════════
# 渲染对话历史
# ═══════════════════════════════════════
for msg in st.session_state.socratic_history:
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

    # 如果是新步骤的第一步尝试，显示问题
    if attempt_count == 0:
        question_text = f"**第 {current_step_idx} 步**：{current_step.get('question', '')}"
        if not st.session_state.socratic_history or \
           st.session_state.socratic_history[-1]["content"] != question_text:
            with st.chat_message("assistant"):
                st.markdown(question_text)
            st.session_state.socratic_history.append({
                "role": "assistant",
                "content": question_text,
            })

    # 接收回答
    if user_answer := st.chat_input("输入你的思考..."):
        # 显示学生回答
        with st.chat_message("user"):
            st.markdown(user_answer)
        st.session_state.socratic_history.append({
            "role": "user",
            "content": user_answer,
        })

        # 判断回答质量
        st.session_state["socratic_attempt_count"] += 1
        result = judge_answer(
            step=current_step,
            student_answer=user_answer,
            attempt_count=st.session_state["socratic_attempt_count"],
        )

        # 累积覆盖和薄弱点
        for pt in result.get("covered_points", []):
            if pt not in st.session_state["socratic_all_covered"]:
                st.session_state["socratic_all_covered"].append(pt)
        for pt in result.get("missing_points", []):
            if pt not in st.session_state["socratic_all_weak"]:
                st.session_state["socratic_all_weak"].append(pt)

        # 显示助教反馈
        with st.chat_message("assistant"):
            st.markdown(result["response"])

            # 如果是 advance 或 simplify，显示质量标签
            quality = result.get("student_answer_quality", "")
            action = result.get("action", "")
            if action == "advance":
                st.caption(f"✅ 回答质量：{quality} | 推进到下一步")
            elif action == "simplify":
                st.caption(f"🔄 回答质量：{quality} | 简化重述")

        st.session_state.socratic_history.append({
            "role": "assistant",
            "content": result["response"],
        })

        # ── 根据 action 决定下一步 ──
        if action == "advance":
            if current_step_idx >= total_steps:
                # 全部完成
                st.session_state["socratic_completed"] = True
                final_result = complete_socratic(
                    socratic_id=socratic_id,
                    covered_points=st.session_state["socratic_all_covered"],
                    weak_points=st.session_state["socratic_all_weak"],
                )
                st.session_state["last_socratic_result"] = final_result
                st.session_state["current_feynman_id"] = "F001"
            else:
                st.session_state["socratic_current_step"] += 1
                st.session_state["socratic_attempt_count"] = 0
        elif action in ("hint", "retry", "simplify"):
            # 留在当前步骤，attempt_count 已递增
            pass

        st.rerun()

# ═══════════════════════════════════════
# 已完成：展示总结 + 导航按钮
# ═══════════════════════════════════════
if completed:
    last_result = st.session_state.get("last_socratic_result", {})

    st.success("🎉 苏格拉底引导完成！")

    with st.expander("📊 学习总结", expanded=True):
        summary = last_result.get("summary", "")
        if summary:
            st.markdown(f"**核心结论**\n\n{summary}")

        covered = last_result.get("covered_points", [])
        weak = last_result.get("remaining_weak_points", [])
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**已掌握知识点**")
            for pt in covered:
                st.markdown(f"- ✅ {pt}")
        with col_b:
            st.markdown("**仍需加强**")
            for pt in weak:
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
    for key in [
        "socratic_current_step", "socratic_attempt_count",
        "socratic_all_covered", "socratic_all_weak",
        "socratic_completed", "socratic_history",
        "last_socratic_result",
    ]:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()
