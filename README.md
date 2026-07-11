# 材智（CaiZhi Agent）—— 材料学科 AI 学习智能体

> 面向材料专业学生的智能学习系统 —— 从"获得答案"到"理解因果链、讲清知识、迁移应用"。
>
> 清华大学 · 本科生作品 · AI+材料大赛参赛项目
>
> 🔗 **GitHub**: [https://github.com/Jesse-dry/CaiZhi-Agent](https://github.com/Jesse-dry/CaiZhi-Agent)

---

## 项目简介

本项目针对材料科学与工程专业的学习特点，基于**中英双语教材知识库**、**材料学科知识图谱**与**大语言模型（LLM）**，构建了一个集以下六大核心能力于一体的 AI 学习智能体：

| 核心能力 | 说明 |
|---|---|
| **智能答疑** | 基于教材知识库的精准问答，拒绝"幻觉"，所有回答有据可查 |
| **错题溯源诊断** | 不止判断对错，更追溯错误背后的知识薄弱点与典型迷思概念 |
| **苏格拉底式引导** | 通过层层追问，引导学生自己发现答案，培养材料科学因果推理能力 |
| **费曼学习法评价** | 让学生用"自己的话"讲解概念，AI 评估其是否真正理解而非机械记忆 |
| **知识图谱** | 构建材料学科知识点关联网络，可视化知识结构，辅助查漏补缺 |
| **个性化学习路径推荐** | 基于学生画像（知识点掌握度、错题分布、学习风格），动态推荐下一步学习内容 |

**核心理念**：大模型不应只是"答案生成器"，而应成为引导学生深入理解材料科学内在逻辑的**教学智能体**。

---

## 技术架构（四层 + API + 前端规划）

2026-07-11 完成四层架构重构，并设计了完整的 SSE 流式事件协议、EventSink 统一事件出口、REST API 边界和前端两层状态架构。

```
┌──────────────────────────────────────────────────────────────┐
│  展示层 pages/ (Streamlit)    │  api/ (FastAPI)              │
│                               │  frontend/ (React/Vue 规划)   │
├──────────────────────────────────────────────────────────────┤
│  服务层 services/             │  工作流层 workflows/          │
│  类化 + 构造器注入 + EventSink │  学习闭环状态机 + 守卫条件    │
├──────────────────────────────────────────────────────────────┤
│  数据协议 schemas/            │  仓储接口 repositories/       │
│  StreamEvent / EventSink /    │  ABC 抽象（知识库/RAG/会话）  │
│  Pydantic v2 统一请求/响应    │                              │
├──────────────────────────────────────────────────────────────┤
│  基础设施 infrastructure/     │  领域逻辑                     │
│  ChromaDB / LLM / 文件/会话   │  agents/ rag/ knowledge/      │
│  / EventSink 实现             │                              │
├──────────────────────────────────────────────────────────────┤
│  数据 data/ database/ vector_store/ configs/                 │
└──────────────────────────────────────────────────────────────┘
```

**当前调用链**：`Streamlit pages → services/workflows → agents/rag/repositories → infrastructure`

**未来调用链**：`React/Vue → FastAPI → services/workflows → agents/rag/repositories → infrastructure`

**关键原则**：
- `services/`、`workflows/`、`rag/`、`agents/` 不依赖 Streamlit 或 FastAPI
- 业务逻辑通过构造器注入依赖（`RAGRepository`, `KnowledgeRepository`, `LLMClient`），与传输层彻底解耦
- `EventSink` 协议统一事件出口 — Service 不知道下游是 Streamlit 占位符还是 SSE 队列
- `LearningSession`（Pydantic）是权威会话模型；`st.session_state` 仅是本地缓存
- 所有跨层数据使用 `schemas/` Pydantic 模型
- API 围绕**资源和操作**设计，不按页面名称映射

### SSE 流式事件协议

2026-07-11 设计。细粒度流式事件，一次 API 调用内推送检索进度和生成增量：

```
run.started → retrieval.started → retrieval.source_found×N → retrieval.completed
→ generation.started → generation.delta×N → generation.section_completed×N → run.completed
```

**StreamEvent** 统一事件模型：`event_id` (evt_0008)、`run_id` (run_abc123)、`sequence` (单调递增)、`event` (点号分隔类型)、`stage`、`payload`。支持 SSE `Last-Event-ID` 断线重连。

**EventSink 协议**：`async emit(event: StreamEvent) → None`。四种实现 — `NullEventSink`（静默）、`StreamlitEventSink`（st.empty 渲染）、`RunStoreEventSink`（SSE 缓冲）、`QueueEventSink`（背压控制）。

### REST API 设计

围绕资源和操作设计，不按页面映射：

| 端点 | 说明 | 状态 |
|------|------|------|
| `POST /api/v1/sessions/` | 创建会话 | ✅ |
| `GET /api/v1/sessions/{id}` | 获取会话 | ✅ |
| `DELETE /api/v1/sessions/{id}` | 删除会话 | ✅ |
| `POST /api/v1/sessions/{id}/qa-runs` | 创建答疑任务 → 返回 run_id + events_url | ✅ |
| `GET /api/v1/runs/{id}/events` | SSE 流式事件 | ✅ |
| `GET /api/v1/runs/{id}` | 获取完整结果 | ✅ |
| `DELETE /api/v1/runs/{id}` | 删除 run | ✅ |
| `POST /api/v1/sessions/{id}/diagnoses` | 提交错题诊断 | 🔧 占位 |
| `POST /api/v1/sessions/{id}/socratic/answers` | 提交苏格拉底回答 | 🔧 占位 |
| `POST /api/v1/sessions/{id}/feynman-evaluations` | 提交费曼评价 | 🔧 占位 |
| `GET /api/v1/sessions/{id}/recommendations` | 获取学习路径 | 🔧 占位 |
| `GET /api/v1/sessions/{id}/knowledge-graph` | 获取知识图谱 | ✅ |

**模式**：`POST 创建任务 → GET SSE 订阅`—— 副作用和订阅分离，支持断线重连。

### 状态机 + 守卫条件

教学闭环由 `workflows/learning_loop.py` 后端强制执行：

```
QA → DIAGNOSIS ─┬─(正确)→ FEYNMAN ─┬─(≥60分)→ RECOMMENDATION → COMPLETED
                 │                   │
                 ├─(错误)→ SOCRATIC ←┘─(<60分, 回炉补救)
                 │                   ↑
                 └───────────────────┘
```

即使前端绕过页面顺序发送请求，后端也会拒绝非法状态迁移。

---

## 项目结构

```
CaiZhi-Agent/
│
├── app.py                         # Streamlit 主入口
│
├── pages/                         # 展示层 —— 纯 UI，不含业务逻辑
│   ├── 1_Smart_Answering.py       # 智能答疑
│   ├── 2_Error_Diagnosis.py       # 错题诊断
│   ├── 3_Socratic_Guidance.py     # 苏格拉底引导
│   ├── 4_Feynman_Evaluation.py    # 费曼评价
│   ├── 5_Knowledge_Graph.py       # 知识图谱（stub）
│   ├── 6_Learning_Path_Recommendation.py  # 学习路径推荐
│   ├── 7_Debug.py                 # 知识库调试
│   └── 8_RAG_Debug.py             # RAG 检索调试
│
├── services/                      # 服务层 —— 类化 + 构造器注入 + EventSink
│   ├── rag_service.py             # ✅ RAG 检索服务封装
│   ├── qa_service.py              # ✅ QAService 类（DI + async + event_sink）
│   ├── diagnosis_service.py       # ✅ 错题诊断（待类化）
│   ├── socratic_service.py        # ✅ 苏格拉底引导（待类化）
│   ├── feynman_service.py         # ✅ 费曼评价（待类化）
│   └── recommendation_service.py  # ✅ 学习路径推荐（待类化）
│
├── schemas/                       # ★ 统一数据协议（Pydantic v2）
│   ├── common.py                  #   共享枚举和值对象
│   ├── learning_session.py        #   LearningSession 权威会话模型
│   ├── qa.py                      #   智能答疑请求/响应
│   ├── diagnosis.py               #   错题诊断请求/响应
│   ├── socratic.py                #   苏格拉底引导请求/响应
│   ├── feynman.py                 #   费曼评价请求/响应
│   ├── recommendation.py          #   学习路径推荐请求/响应
│   ├── events.py                  #   StreamEvent + EventEmitter（SSE 事件）
│   ├── event_sink.py              #   EventSink 协议 + NullEventSink
│   └── runs.py                    #   Run 生命周期模型（CreateRunRequest 等）
│
├── workflows/                     # ★ 学习闭环状态机（带守卫条件）
│   ├── state_machine.py           #   通用有限状态机
│   └── learning_loop.py           #   5 阶段状态机 + 分支守卫
│
├── repositories/                  # ★ 数据存取抽象接口（ABC）
│   ├── knowledge_repo.py          #   知识库接口
│   ├── rag_repo.py                #   RAG 检索接口
│   └── session_repo.py            #   会话存储接口
│
├── infrastructure/                # ★ 具体实现层
│   ├── chroma_store.py            #   ChromaDB RAG 实现（RAGRepository）
│   ├── llm_client.py              #   LLM 客户端封装（占位）
│   ├── file_knowledge_repo.py     #   文件知识库实现（KnowledgeRepository）
│   ├── memory_session.py          #   内存会话存储（SessionRepository）
│   ├── sqlite_session.py          #   SQLite 会话存储（占位）
│   └── event_sinks.py             #   EventSink 具体实现（Streamlit/RunStore/Queue/Callback）
│
├── api/                           # ★ FastAPI — 资源路由 + DI + SSE
│   ├── main.py                    #   FastAPI 应用入口 + 路由注册
│   ├── dependencies.py            #   Depends() 依赖注入容器
│   ├── sse.py                     #   SSE StreamingResponse 工具
│   ├── run_store.py               #   内存 Run 存储 + 事件缓冲 + 重连
│   └── routers/                   #   APIRouter 模块（一个资源一个文件）
│       ├── sessions.py            #   CRUD /sessions
│       ├── qa.py                  #   POST /sessions/{id}/qa-runs
│       ├── diagnosis.py           #   POST /sessions/{id}/diagnoses
│       ├── socratic.py            #   POST /sessions/{id}/socratic/answers
│       ├── feynman.py             #   POST /sessions/{id}/feynman-evaluations
│       ├── recommendations.py     #   GET  /sessions/{id}/recommendations
│       ├── knowledge_graph.py     #   GET  /sessions/{id}/knowledge-graph
│       └── runs.py                #   GET/DELETE /runs/{id} + SSE events
│
├── frontend/                      # ★ React/Vue 规划（两层状态架构）
│   └── README.md                  #   技术栈 + store 设计 + SSE 消费模式
│
├── rag/                           # ✅ RAG 管线
│   ├── pdf_parser.py              #   PDF→Markdown（Marker）
│   ├── chunker.py                 #   语义分块
│   ├── prepare_chunks.py          #   全流程编排
│   ├── build_vector_store.py      #   ChromaDB + BGE-m3
│   ├── bilingual_retriever.py     #   双语检索 + 术语扩展
│   ├── check_chunks.py            #   Chunk 质量统计
│   ├── image_captioner.py         #   图表 Caption（Qwen-VL-Max）
│   ├── fix_metadata.py            #   修复向量库 metadata
│   └── enrich_images.py           #   图片索引补全
│
├── agents/                        # AI 推理层 —— 全部为 stub
│
├── knowledge/                     # 知识增强层
│   ├── knowledge_graph.py         # ✅ 知识图谱查询
│   ├── terminology.py             # ✅ 术语查询
│   ├── term_expander.py           # ✅ 术语扩展
│   ├── misconception_mapper.py    # ✅ 错题-误区映射
│   └── prompt_builder.py          # ✅ RAG Prompt 组装
│
├── data/                          # 数据
│   ├── textbooks/                 #   教材 PDF（不入库）
│   ├── processed/                 #   RAG 产出（不入库）
│   ├── terms.csv                  #   术语表
│   ├── knowledge_graph.json       #   知识图谱
│   ├── questions.json             #   题库
│   ├── socratic.json              #   苏格拉底引导
│   └── feynman.json               #   费曼评价标准
│
├── vector_store/                  # ChromaDB 向量库（不入库）
├── utils/state.py                 # Streamlit 会话适配器
├── database/                      # 关系数据库（stub）
├── configs/                       # 配置文件
├── check_headings.py              # 标题校验工具
├── fix_en_headings.py             # 英文标题修复工具
├── docs/                          # 文档
│
├── requirements.txt
├── .env                           # API Key（不入库）
├── .gitignore
├── CLAUDE.md                      # Claude Code 项目指南
└── README.md
```

---

## 快速开始

> ⚠️ 项目处于 V1 最小可行性测试阶段，聚焦"铁碳相图与钢的热处理"知识单元。
> RAG 管线 **已在 RTX 5090 服务器上执行**，两本教材 PDF→Markdown 转换完成（1,636 张图表 + 4.8 MB Markdown）。
> 以下为首次部署步骤，如需重新执行 PDF 转换请参考 `CLAUDE.md`。

### 1. 安装依赖

```bash
git clone https://github.com/Jesse-dry/CaiZhi-Agent.git
cd CaiZhi-Agent

python -m venv venv
source venv/bin/activate   # Linux/Mac
# venv\Scripts\activate    # Windows

pip install -r requirements.txt
```

### 2. 配置 API Key

创建 `.env` 文件：
```bash
ANTHROPIC_API_KEY=sk-ant-...
```

### 3. 准备教材 PDF

将教材 PDF 放入对应目录：
- `data/textbooks/zh/` — 中文教材
- `data/textbooks/en/` — 英文教材

### 4. 运行 RAG 管线

```bash
# Step 1: PDF → Markdown（⚠️ 需 8GB+ RAM，建议在服务器执行）
python -m rag.prepare_chunks --pdf-only

# 检查 Markdown 质量 —— 用 check_headings.py 提取大纲
python check_headings.py
# 核验：① 章节标题是否识别为 #/##/###  ② 大纲是否与目录对应

# Step 2: Markdown → 语义 Chunks
python -m rag.prepare_chunks --chunk-only

# Step 3: Chunk 质量检查
python -m rag.check_chunks
# 健康指标：空chunk=0，平均长度 500-1500 字符，最大<6000，metadata缺失=0

# Step 4: 构建向量库（推荐 DashScope API，零本地内存）
python -m rag.build_vector_store --backend dashscope
# 或使用本地 BGE-M3 模型：
# python -m rag.build_vector_store --backend local
```

### 5. 启动应用

```bash
streamlit run app.py
```

进入 **RAG Debug** 页（第 8 页）验证检索效果。

---

## V1 实现状态

### RAG 管线

| 模块 | 状态 | 说明 |
|---|---|---|
| RAG 管线 `rag/` | ✅ 代码就绪 | Marker + 语义分块 + BGE-m3 + 双语检索 |
| RAG 管线执行 | ✅ 已完成 | RTX 5090 服务器，两本教材 PDF→MD 成功 |
| 向量库 metadata 修复 | ✅ 已完成 | `fix_metadata.py` 补全章节/图片字段，免重编码 |
| 图片索引补全 | ✅ 已完成 | `enrich_images.py` 补全 page/nearby_header/caption_status |
| 图片 Caption | ✅ 已完成 | Qwen-VL-Max 标注 935 张图表 |
| 标题质量校验 | ✅ 已通过 | `check_headings.py` 提取大纲，中文层级优秀 |
| 英文标题修复 | ✅ 已完成 | `fix_en_headings.py` 修复 OCR 噪音 + 章节升级 |
| RAG Debug (页 8) | ✅ 已实现 | 术语 + 章节 + 双语结果 + 图表描述 + 图片字段 |
| RAG 检索服务 | ✅ 已实现 | 术语扩展 → 双语检索 → 合并排序 + 图片透传 |

### 学习闭环（五页 + 五服务）

| 页面 | Service | V1 引擎 | 说明 |
|------|---------|---------|------|
| 1. 智能答疑 | `qa_service` | 规则驱动 | `answer_question()` 组合四种数据源，固定 7 区块输出。LLM prompt 已构建，待接入。 |
| 2. 错题诊断 | `diagnosis_service` | JSON 映射 | `submit_answer()` 误区定位 + `misconception_id`，统一键名。 |
| 3. 苏格拉底引导 | `socratic_service` | 关键词匹配 | `judge_answer()` → advance/hint/retry/simplify，S001 链 6 步台阶。 |
| 4. 费曼评价 | `feynman_service` | Checklist 评分 | `evaluate()` 五维度打分（满分 78），`next_question` 追问。 |
| 5. 知识图谱 | — | 🔧 stub | 可视化待做 |
| 6. 学习路径推荐 | `recommendation_service` | 先修关系排序 | 聚合三源薄弱点 → 知识单元 K001-K004 → 拓扑排序。 |
| 7. 调试页面 | — | ✅ 已实现 | 术语表 + 知识图谱数据验证 |

**学习闭环链路**：`答疑(K001,C001,Q001) → 诊断(Q001→S001) → 苏格拉底(S001→F001) → 费曼(F001评分) → 学习路径(聚合排序) → 回到答疑`

### 其他

| 模块 | 状态 | 说明 |
|---|---|---|
| `utils/state.py` | ✅ 已统一 | `last_user_question`, `last_answer`, `last_qa_result`, `last_diagnosis`, `last_socratic_result`, `last_feynman_result`, `last_learning_path` |
| `knowledge/prompt_builder.py` | ✅ 已实现 | 约束型 Prompt — 四种数据源职责边界明确 |
| 知识图谱 | ✅ 已实现 | 8 节点 / 7 边 / 1 因果链 C001 |
| 术语扩展 | ✅ 已实现 | `term_expander` — 查询中英双向匹配 + 因果链节点反查补齐 |
| Agent 层 (`agents/`) | ❌ 全部 stub | 5 个 Agent 文件待 LLM 接入后实现 |
| 数据库 (`database/`) | ❌ stub | 学生记录待接入 |

---

**转换结果**（2026-07-09，RTX 5090）：

| 教材 | Markdown | 图片 |
|------|----------|------|
| 🇨🇳 材料科学基础（清华） | 1.74 MB | 813 张 |
| 🇬🇧 Materials Science (Callister 10e) | 3.13 MB | 823 张 |

质量评估：中文标题层级优秀（H1→H2→H3）。英文原始标题偏扁平（多为 H2），通过 `fix_en_headings.py` 修复后：25 个 H1 章、106 个 H2 节、13 个 H3 小节，22 个章节完整对齐。

---

## RAG 技术方案

> **2026-07-11 更新**：Embedding 已从本地 BGE-M3 迁移至 **DashScope text-embedding-v4 API**。
> - 不再加载 2GB 本地模型，Python 进程内存从 ~2GB 降至 ~70MB
> - 向量库存储位置从 `vector_store/` 改为 `C:\chroma_data\`（ChromaDB Rust HNSW 不支持中文路径）
> - 查询时 DashScope API 优先，网络故障自动 fallback 到本地 BGE-M3
> - 配置：`.env` 中 `DASHSCOPE_API_KEY`（已有），可选 `CHROMA_DATA_DIR` 自定义存储路径

| 环节 | 技术选型 | 说明 |
|---|---|---|
| PDF 解析 | **Marker** (surya OCR) | 视觉 AI 解析，支持双栏排版/公式→LaTeX/表格→Markdown/图片提取 |
| 文本分块 | **MarkdownHeaderTextSplitter** | 按 H1/H2/H3 语义切分，保留章节 metadata |
| Embedding | **DashScope text-embedding-v4**（API） / BGE-m3（fallback） | 1024 维，多语言，API 调用零本地内存，BGE-m3 作为离线 fallback |
| 向量数据库 | **ChromaDB** | 轻量级，本地持久化 |
| 术语扩展 | terms.csv 中英双向匹配 | 查询中自动追加对应翻译 |
| 图表处理 | Claude Vision API（Phase 2） | 为相图/TTT曲线等生成文字描述，存入向量库 |
| 前端 | Streamlit | RAG Debug 页展示检索结果+术语+章节+图表 |

---

## 关键技术选型

| 模块 | 技术方案 |
|---|---|
| 大语言模型 | Claude API / GPT-4o / 开源模型（Qwen、DeepSeek） |
| RAG 框架 | 自建管线（rag/）+ LangChain（分块） |
| 向量数据库 | ChromaDB |
| Embedding | DashScope text-embedding-v4（API）/ BGE-m3（fallback） |
| PDF 解析 | Marker (surya OCR) |
| 知识图谱 | NetworkX + JSON |
| 前端 | Streamlit |

---

## 致谢

本项目受清华大学"因材施教"教学理念启发，致力于将 AI 技术真正融入材料学科教育，帮助学生建立深层理解而非表面记忆。

---

## 开发者

两位清华大学本科生，AI+材料大赛参赛团队。

---

## License

MIT License
