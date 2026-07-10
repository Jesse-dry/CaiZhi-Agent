import streamlit as st

st.set_page_config(
    page_title="错题诊断",
    page_icon="🧩",
    layout="wide"
)

from services.diagnosis_service import get_question_for_page, submit_answer
from utils.state import init_session_state, go_to

init_session_state()

st.title("🧩 错题诊断")

st.write("学生提交答案后，系统会根据错误选项定位误区、缺失知识点和补救路径。")

question_id = "Q001"
question = get_question_for_page(question_id)

if question is None:
    st.error("未找到题目，请检查 data/questions.json")
    st.stop()


st.subheader("题目")
st.markdown(f"**{question['question']}**")

options = question["options"]

selected_option = st.radio(
    "请选择你的答案：",
    options=list(options.keys()),
    format_func=lambda key: f"{key}. {options[key]}"
)

if st.button("提交答案", type="primary"):
    result = submit_answer(question["question_id"], selected_option)
    st.session_state["last_diagnosis"] = result
    st.session_state["current_chain_id"] = result.get("next_chain_id", "C001")
    st.session_state["current_socratic_id"] = result.get("next_socratic_id", "S001")


result = st.session_state.get("last_diagnosis")

if result:
    st.divider()

    if not result.get("success", False):
        st.error(result.get("message", "诊断失败"))
        st.stop()

    if result["is_correct"]:
        st.success("回答正确")
    else:
        st.error("回答错误")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 你的选择")
        st.write(f"{result['selected_option']}. {result['selected_text']}")

    with col2:
        st.markdown("### 正确答案")
        st.write(f"{result['correct_answer']}. {result['correct_text']}")

    st.markdown("### 诊断结果")
    st.info(result["message"])

    if not result["is_correct"]:
        st.markdown("#### 对应误区")
        st.warning(result["misconception"])

        st.markdown("#### 错误原因")
        st.write(result["error_reason"])

        st.markdown("#### 针对性反馈")
        st.write(result["feedback"])

        st.markdown("#### 缺失知识点")
        for point in result["missing_points"]:
            st.write(f"- {point}")

        st.markdown("#### 补救路径")
        if result["remedial_path"]:
            st.code(" → ".join(result["remedial_path"]))

    st.markdown("### 标准解释")
    st.write(result["answer_explanation"])

    st.markdown("### 下一步")

    col3, col4, col5 = st.columns(3)

    with col3:
        if st.button("进入苏格拉底引导", type="primary"):
            st.session_state["socratic_history"] = []
            go_to("socratic")

    with col4:
        if st.button("查看相关知识链"):
            go_to("graph")

    with col5:
        if st.button("直接生成学习路径"):
            go_to("learning_path")