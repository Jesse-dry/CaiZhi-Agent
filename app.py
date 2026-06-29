# app.py
import streamlit as st
from utils.state import init_session_state

# 1. 页面基础配置 (必须是 Streamlit 命令的第一句)
st.set_page_config(
    page_title="AI材料学导师",
    page_icon="🧊",
    layout="wide"
)

# 2. 初始化全局状态
init_session_state()

# 3. 首页内容展示
st.title("🧊 AI 材料学智能导师系统")
st.markdown("""
欢迎来到材料学智能导师系统！本系统致力于帮助你打通 **“工艺—组织—性能”** 的核心因果链。

### 👈 请在左侧侧边栏选择功能模块：
1. **Smart Answering**：基于权威英文教材的材料学 RAG 问答
2. **Error Diagnosis**：一键溯源你的知识盲区并匹配图谱路径
3. **Socratic Guidance**：通过递进式提问启发你的底层逻辑
4. **Feynman's Evaluation**：用你的话讲出来，AI 对你的因果链进行打分
5. **Knowledge Graph**：可视化材料学科知识点关联网络
6. **Learning Path Recommendation**：基于学生画像的个性化学习导航
""")

st.info("当前版本为 V1 最小可行性测试版，主要聚焦『铁碳相图与钢的热处理』知识单元。")