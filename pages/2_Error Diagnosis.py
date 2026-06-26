# pages/2_Error Diagnosis.py
# -*- coding: utf-8 -*-
import streamlit as st

st.title("错题溯源诊断")

st.caption("💡 不止判断对错——追溯错误背后的知识薄弱点与迷思概念")

st.markdown("### 📝 本期错题回顾")
st.info("**题目**：淬火后钢的硬度提高，主要原因是什么？")

# 单选组件
option = st.radio(
    "你的选择是：",
    ["A. 晶粒显著细化", "B. 形成马氏体", "C. 形成粗大珠光体", "D. 碳含量降低"],
    index=None
)

# 触发诊断逻辑
if option == "A. 晶粒显著细化":
    st.error("❌ 回答错误！系统已为你生成诊断报告：")
    st.markdown("""
    **【误区诊断】**
    你把淬火强化误认为晶粒细化强化。

    **【真正原因缺失】**
    `马氏体转变` ➔ `晶格畸变` ➔ `位错运动受阻` ➔ `硬度提高`

    **【建议补救】**
    建议前往左侧 **"苏格拉底引导"** 重新梳理工艺与组织的关系。
    """)

elif option == "B. 形成马氏体":
    st.success("✅ 回答正确！马氏体是淬火提高硬度的核心原因。")

elif option == "C. 形成粗大珠光体":
    st.error("❌ 回答错误！系统已为你生成诊断报告：")
    st.markdown("""
    **【误区诊断】**
    你不理解冷却速度对组织转变的影响——粗大珠光体是缓慢冷却（退火/正火）的产物，而非淬火。

    **【真正原因缺失】**
    `快速冷却` ➔ `扩散受限` ➔ `马氏体（非珠光体）` ➔ `硬度提高`

    **【建议补救】**
    复习快速冷却与扩散型/无扩散型相变的区别，区分不同冷却速度对应的组织产物。
    """)

elif option == "D. 碳含量降低":
    st.error("❌ 回答错误！系统已为你生成诊断报告：")
    st.markdown("""
    **【误区诊断】**
    你误以为淬火会改变钢的碳含量——热处理过程中成分不发生变化，变化的是组织结构与碳的分布状态。

    **【真正原因缺失】**
    `热处理不改变成分` ➔ `改变的是组织` ➔ `碳原子分布状态变化` ➔ `马氏体过饱和`

    **【建议补救】**
    复习热处理过程中成分变化与组织变化的本质区别。
    """)

# TODO: 替换为 services/diagnosis_service.py 的真实调用
# from services.diagnosis_service import diagnose
# result = diagnose(question_id=”Q001”, student_answer=option, user_id=st.session_state.user_id)