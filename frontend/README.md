# 前端 (Frontend)

## 未来迁移目标

当前前端为 **Streamlit** (`pages/` 目录)，后续将迁移到现代前端技术栈。

## 技术栈选择

| 层级 | 技术 | 说明 |
|------|------|------|
| 框架 | **React 18+** 或 **Vue 3** | 组件化 UI |
| 构建 | **Vite** | 快速 HMR + 构建 |
| 状态管理 | **Zustand** (React) / **Pinia** (Vue) | 全局状态替代 st.session_state |
| 路由 | **React Router** / **Vue Router** | SPA 页面路由 |
| 实时通信 | **SSE** (Server-Sent Events) | 流式 LLM 响应 |
| UI 组件库 | **Ant Design** / **Naive UI** | 教学场景友好 |
| 图表 | **ECharts** / **D3.js** | 知识图谱可视化 |
| 类型 | **TypeScript** | 类型安全 |

## 页面结构 (对应 Streamlit pages)

```
src/
  pages/
    SmartAnswering.tsx     ← 1_Smart_Answering.py
    ErrorDiagnosis.tsx     ← 2_Error_Diagnosis.py
    SocraticGuidance.tsx   ← 3_Socratic_Guidance.py
    FeynmanEvaluation.tsx  ← 4_Feynman_Evaluation.py
    KnowledgeGraph.tsx     ← 5_Knowledge_Graph.py
    LearningPath.tsx       ← 6_Learning_Path_Recommendation.py
  components/
    chat/                  # 聊天组件
    diagnosis/             # 诊断组件
    evaluation/            # 评价组件
    graph/                 # 图谱可视化组件
  stores/
    sessionStore.ts        # 全局会话状态 (替代 st.session_state)
    learningLoopStore.ts   # 学习闭环状态机
  api/
    client.ts              # FastAPI HTTP 客户端
    sse.ts                 # SSE 流式连接
```

## 迁移要点

1. **状态管理**：`st.session_state` → Zustand/Pinia store，后端由 FastAPI + SQLite/Redis 管理
2. **页面路由**：`st.switch_page()` → React Router / Vue Router
3. **流式响应**：`st.chat_message()` 占位 → SSE 实时渲染
4. **进度条**：`st.progress()` → 自定义进度组件
5. **导航**：`go_to()` → `<Link>` / `router.push()`

## 当前状态

- Streamlit 页面 (`pages/`) 是当前生产前端
- 本目录为占位，等待后端 API 稳定后启动前端迁移
