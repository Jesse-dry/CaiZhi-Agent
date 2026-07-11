# 前端 (Frontend)

## 未来迁移目标

当前前端为 **Streamlit** (`pages/` 目录)，后续将迁移到现代前端技术栈。

## 技术栈选择

| 层级 | 技术 | 说明 |
|------|------|------|
| 框架 | **React 18+** 或 **Vue 3** | 组件化 UI |
| 构建 | **Vite** | 快速 HMR + 构建，内置 esbuild 编译 TS |
| 远程状态 | **TanStack Query** (React) / **Vue Query** | 服务端数据缓存、自动去重、后台刷新 |
| 客户端状态 | **Zustand** (React) / **Pinia** (Vue) | 轻量 UI 状态，不存服务端数据 |
| 路由 | **React Router** / **Vue Router** | SPA 页面路由 |
| 实时通信 | **SSE** (EventSource) | 流式 LLM 响应，原生 API 无需库 |
| UI 组件库 | **Ant Design** / **Naive UI** | 教学场景友好 |
| 图表 | **ECharts** / **D3.js** | 知识图谱可视化 |
| 类型 | **TypeScript** | 类型安全，可从 OpenAPI schema 生成 |

---

## 状态架构：两层划分（核心原则）

**不要把所有状态塞进一个 globalStore。** 严格分成两层：

### 第 1 层：服务端状态（后端是权威，前端只缓存）

> 由 **TanStack Query / Vue Query** 管理，不是 Zustand/Pinia。

| 数据 | 来源 | 缓存策略 |
|------|------|---------|
| LearningSession | `GET /api/v1/sessions/{id}` | staleTime: 5min，页面切换时后台刷新 |
| QAResult | `GET /api/v1/runs/{run_id}` | staleTime: Infinity（只读历史） |
| DiagnosisResult | 同上 | 同上 |
| Socratic 历史 | 同上 | 同上 |
| FeynmanResult | 同上 | 同上 |
| LearningPath | 同上 | 同上 |
| RAG 来源列表 | 包含在 QAResult.sources 中 | 不单独缓存 |
| Run 列表 | `GET /api/v1/sessions/{id}/runs` | staleTime: 30s |

**关键规则：**
- **永远不要**把 `LearningSession` 完整复制到 Zustand/Pinia store
- TanStack Query 的 `queryClient.getQueryData()` 就是唯一缓存，避免重复状态
- 同一份数据在多个组件中出现 → 用同一个 `useQuery` key，不是各自存一份

### 第 2 层：客户端 UI 状态（前端是权威）

> 由 **Zustand / Pinia** 管理，按领域拆分为 4 个轻量 store。

#### `stores/uiStore.ts` — 界面状态

```typescript
interface UIState {
  // 页面
  currentPage: 'qa' | 'diagnosis' | 'socratic' | 'feynman' | 'recommendation' | 'graph';
  sidebarCollapsed: boolean;

  // 教材来源面板
  expandedSources: string[];        // 当前展开的 chunk_id 列表
  activeSourceTab: 'zh' | 'en';     // 来源语言切换

  // 错误提示
  toasts: Toast[];

  // 输入框
  draftQuestion: string;            // 用户正在输入但未提交的问题
  draftAnswer: string;              // 用户正在输入但未提交的答案（费曼/苏格拉底）
}
```

#### `stores/streamStore.ts` — 流式输出状态

```typescript
interface StreamState {
  // 当前活跃的 SSE 连接
  activeRunId: string | null;
  connectionStatus: 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'closed';

  // 流式输出缓冲区（逐 delta 追加，完成后清空）
  streamBuffer: {
    short_answer: string;
    principle: string;
    causal_chain: string;
    key_terms: string;
  };

  // 检索来源（逐条到达，实时展示）
  liveSources: SourceReference[];

  // 进度
  currentStage: 'retrieval' | 'generation' | 'completed' | null;
  lastEventId: string | null;       // 用于 SSE 重连
}
```

#### `stores/userStore.ts` — 用户偏好

```typescript
interface UserState {
  userId: string;
  sessionId: string;
  preferredLanguage: 'zh' | 'en' | 'auto';
  theme: 'light' | 'dark';
}
```

#### `stores/learningStore.ts` — 学习流程导航（轻量）

```typescript
interface LearningFlowState {
  // 只存"指向"服务端数据的 ID，不存数据本身
  currentChainId: string | null;
  currentQuestionId: string | null;
  currentSocraticId: string | null;
  currentFeynmanId: string | null;

  // 学习闭环当前位置（用于导航高亮）
  activeStage: LearningStage;
  stageHistory: LearningStage[];     // 已完成的阶段列表
}
```

---

## 数据流示意

```
┌─────────────────────────────────────────────────────────┐
│  服务端状态（TanStack Query 缓存）                        │
│                                                         │
│  useQuery(['session', id])    → LearningSession         │
│  useQuery(['run', runId])     → QAResult                │
│  useQuery(['runs', sessionId]) → RunListResponse        │
│                                                         │
│  ← 后端是权威，前端不修改，只缓存和展示                    │
└─────────────────────────────────────────────────────────┘
                         │
                         │ 组件通过 useQuery 读取
                         ▼
┌─────────────────────────────────────────────────────────┐
│  组件                                                    │
│                                                         │
│  QA 页面:                                                │
│    useQuery(['run', runId])  → 渲染回答卡片               │
│    useStreamStore()          → 渲染流式文本缓冲区          │
│    useUIStore()              → 管理输入框 draft           │
│                                                         │
│  Diagnosis 页面:                                          │
│    useQuery(['run', runId])  → 渲染诊断结果               │
│    useLearningStore()        → 读取 currentQuestionId     │
└─────────────────────────────────────────────────────────┘
                         │
                         │ 用户操作 → Hook 调用 API
                         ▼
┌─────────────────────────────────────────────────────────┐
│  客户端 UI 状态（Zustand/Pinia store）                    │
│                                                         │
│  uiStore        — 侧边栏、展开/折叠、draft、toast        │
│  streamStore    — SSE 缓冲区、连接状态、liveSources       │
│  userStore      — userId, sessionId, 偏好               │
│  learningStore  — 导航指针（ID only，不存数据）           │
│                                                         │
│  ← 前端是权威，不与服务端数据重复                          │
└─────────────────────────────────────────────────────────┘
```

---

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
    chat/                  # 聊天组件（流式文本渲染）
    diagnosis/             # 诊断组件（选项、误区卡片）
    evaluation/            # 评价组件（5 维度进度条）
    graph/                 # 图谱可视化组件
    sources/               # 教材来源面板（展开/折叠）
    layout/                # 布局组件（侧边栏、导航）
  hooks/
    useSSE.ts              # EventSource 封装（连接、重连、解析）
    useRunStream.ts        # POST 创建 + SSE 订阅完整流程
    useLearningFlow.ts     # 学习闭环导航
  stores/
    uiStore.ts             # 界面状态
    streamStore.ts         # 流式缓冲区
    userStore.ts           # 用户偏好
    learningStore.ts       # 学习流程导航
  api/
    client.ts              # fetch 封装 + 错误处理
    queries.ts             # TanStack Query hooks（useSession, useRun, ...）
    mutations.ts           # TanStack Mutation hooks（createRun, submitAnswer, ...）
```

---

## SSE 消费模式

```typescript
// hooks/useRunStream.ts
export function useRunStream(sessionId: string) {
  const queryClient = useQueryClient();
  const streamStore = useStreamStore();

  const start = useMutation({
    mutationFn: async (question: string) => {
      // 1. POST 创建任务
      const res = await fetch(`/api/v1/sessions/${sessionId}/qa-runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });
      return res.json() as Promise<RunCreated>;
    },
    onSuccess: (data) => {
      // 2. 打开 SSE 连接
      streamStore.setActiveRun(data.run_id);
      streamStore.setStatus('connecting');

      const es = new EventSource(data.events_url);

      es.addEventListener('retrieval.source_found', (e) => {
        const event = JSON.parse(e.data);
        streamStore.addLiveSource(event.payload);  // 实时展示来源
      });

      es.addEventListener('generation.delta', (e) => {
        const event = JSON.parse(e.data);
        streamStore.appendDelta(event.payload.section, event.payload.delta);
      });

      es.addEventListener('run.completed', (e) => {
        const event = JSON.parse(e.data);
        // 3. 写入 TanStack Query 缓存（服务端状态）
        queryClient.setQueryData(['run', data.run_id], event.payload.result);
        streamStore.setStatus('closed');
        streamStore.clearBuffer();
        es.close();
      });

      es.addEventListener('run.failed', (e) => {
        const event = JSON.parse(e.data);
        streamStore.setStatus('closed');
        uiStore.addToast({ type: 'error', message: event.payload.error });
        es.close();
      });
    },
  });

  return { start, ...streamStore };
}
```

---

## 迁移要点

1. **状态管理**：`st.session_state` → TanStack Query（服务端数据） + Zustand（UI 状态），严格两层
2. **页面路由**：`st.switch_page()` → React Router / Vue Router
3. **流式响应**：`st.chat_message()` 占位 → SSE `EventSource` + streamStore 缓冲区
4. **进度条**：`st.progress()` → 自定义进度组件（读取 streamStore.currentStage）
5. **导航**：`go_to()` → `<Link>` / `router.push()` + learningStore 更新
6. **避免重复**：LearningSession 只在 TanStack Query 中存一份，组件通过 `useQuery` 共享

## 当前状态

- Streamlit 页面 (`pages/`) 是当前生产前端
- 本目录为架构规划，等待后端 API 稳定后启动前端迁移
