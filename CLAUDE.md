# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

**CaiZhi Agent (材智)** — an AI-powered learning assistant for Materials Science & Engineering students, built for the Tsinghua "AI+Materials" competition. The core philosophy: guide students from "getting answers" to "understanding causal chains, explaining knowledge clearly, and transferring application."

Six core capabilities: Smart Answering (RAG), Error Diagnosis (misconception tracing), Socratic Guidance, Feynman Evaluation, Knowledge Graph, and Learning Path Recommendation.

**Current status**: V1 minimal-viable-test, single knowledge unit: "Fe-C phase diagram and heat treatment of steel." RAG pipeline **fully executed locally (Windows)** — PDF→Markdown (on 5090 server) → Image Captioning (935 figures via Qwen-VL-Max) → Semantic Chunking (5692 chunks) → ChromaDB vector store built and verified. **All 5 learning-loop pages + services are functional** (rule-driven, LLM-ready interfaces). Agent layer is still all stubs. **Next step**: wire LLM calls to replace keyword-based judges with real model inference.

## Commands

```bash
# Run the app
streamlit run app.py

# Install dependencies (in a venv)
pip install -r requirements.txt

# RAG pipeline (PDF→Markdown already done on 5090 server):
python -m rag.prepare_chunks --chunk-only   # Step 2: Markdown → semantic chunks
python -m rag.check_chunks                  # Step 3: quality check before building vector store
python -m rag.build_vector_store --backend dashscope   # Step 4: build ChromaDB (API, recommended)
# python -m rag.build_vector_store --backend local     # Step 4 alt: local BGE-M3

# Image captioning (already executed, re-run if images change):
python -m rag.image_captioner --all         # Caption all Figure images (zh+en)

# Verify retrieval:
python -c "from rag.bilingual_retriever import BilingualRetriever; r = BilingualRetriever(); print(r.retrieve('淬火'))"
```

## 5090 Server

The RAG pipeline was executed on a rented NVIDIA RTX 5090 server (Ubuntu 22.04). Key notes for re-deployment:

- **IP**: 36.103.234.113, **user**: ubuntu, **port**: 22
- **GPU**: RTX 5090 (32GB VRAM), Driver 595.58.03
- **CUDA**: 12.8 and 13.0 installed (`/usr/local/cuda-12.8`, `/usr/local/cuda-13.0`). Default is 13.0 — **must use 12.8** for PyTorch compatibility.
- **No Docker, no conda** — used `python3.10-venv` directly.
- **PyTorch**: installed 2.11.0+cu128 from `https://download.pytorch.org/whl/cu128`. The 820MB torch wheel was pre-downloaded via `wget -c` due to slow international bandwidth, then `pip install --no-deps` + deps separately.
- **NCCL**: PyTorch cu128 ships nccl 2.28.9 — it worked out of the box (no manual compilation needed, unlike the docs warned).
- **Mirrors**: pip → `https://pypi.tuna.tsinghua.edu.cn/simple`, HuggingFace → `https://hf-mirror.com` (set `HF_ENDPOINT`).
- **Disk**: 49GB total, ~6GB free after everything. Clean `~/.cache/pip/` after install to free space.

Full setup script: `server_setup.sh` (committed, run on server with `bash server_setup.sh`).

## Architecture: Four-layer + future API/frontend

The project was refactored (2026-07-11) into a four-layer clean architecture, ready for migration from Streamlit to FastAPI + React/Vue. SSH event protocol, EventSink pattern, and REST API boundaries were designed 2026-07-11.

```
┌──────────────────────────────────────────────────────────────┐
│  PRESENTATION (current)         │  API (future)              │
│  pages/                         │  api/                      │
│  Streamlit UI only — no logic   │  FastAPI endpoints         │
├──────────────────────────────────────────────────────────────┤
│  SERVICES                       │  WORKFLOWS                 │
│  services/                      │  workflows/                │
│  Use-case orchestration         │  Learning-loop state       │
│  (no Streamlit imports!)        │  machine + guard conditions│
├──────────────────────────────────────────────────────────────┤
│  DOMAIN SCHEMAS                 │  REPOSITORIES (interfaces) │
│  schemas/                       │  repositories/             │
│  Pydantic v2 models — all       │  ABCs for knowledge, RAG,  │
│  request/response/event types   │  session persistence       │
├──────────────────────────────────────────────────────────────┤
│  INFRASTRUCTURE                 │  DOMAIN LOGIC              │
│  infrastructure/                │  agents/ (constrained AI)   │
│  ChromaDB, LLM client,          │  knowledge/ (graph, terms, │
│  file knowledge repo,           │  misconception mapper,     │
│  memory/SQLite session store,   │  prompt builder)           │
│  event sinks                    │  rag/ (PDF→MD→chunk→vector) │
├──────────────────────────────────────────────────────────────┤
│  DATA                           │  STATIC ASSETS             │
│  database/ (stubs)              │  data/ (JSON, CSV)         │
│  vector_store/ (ChromaDB)       │  configs/                  │
└──────────────────────────────────────────────────────────────┘
```

**Call chain — current:**
```
Streamlit pages → services / workflows → agents / rag / repositories → infrastructure
```

**Call chain — future:**
```
React/Vue → FastAPI → services / workflows → agents / rag / repositories → infrastructure
```

**Key rules:**
- `services/`, `workflows/`, `rag/`, `agents/` must NOT import `streamlit`
- `st.session_state` is a local UI cache only; `LearningSession` (Pydantic model) is the canonical session
- All cross-layer data uses Pydantic `schemas/` models — no bare dicts
- `repositories/` defines ABCs; `infrastructure/` provides concrete implementations

### Directory map

| Layer | Directory | Role |
|-------|-----------|------|
| Presentation | `pages/` | Streamlit UI (current). 纯展示层：读输入 → 调 service → 展示结果 → 存 UI 临时状态。`utils/state.py` is the Streamlit adapter. |
| API | `api/` | FastAPI REST API. 5 个端点已接入 service 层（与 Streamlit 复用同一套业务逻辑），其余端点就绪。 |
| Frontend | `frontend/` | React/Vue + Vite placeholder (future). `frontend/README.md` with tech-stack plan. |
| Services | `services/` | Use-case orchestration. 5 services (qa/diagnosis/socratic/feynman/recommendation) + rag_service. 函数式/类化混合；与传输层无关，Streamlit 和 FastAPI 共享同一套调用。 |
| Workflows | `workflows/` | `state_machine.py` (generic FSM) + `learning_loop.py` (5-stage state machine with guard-condition branching: QA→DIAGNOSIS→SOCRATIC↔FEYNMAN→RECOMMENDATION→COMPLETED). Backend-enforced — rejects illegal transitions. |
| Schemas | `schemas/` | Unified data protocol. Pydantic v2 BaseModel for all request/response/event/session types. Split by domain: `common.py`, `qa.py`, `diagnosis.py`, `socratic.py`, `feynman.py`, `recommendation.py`, `learning_session.py`, `events.py`. |
| Repositories | `repositories/` | Abstract interfaces (ABC): `knowledge_repo.py`, `rag_repo.py`, `session_repo.py`. |
| Infrastructure | `infrastructure/` | Concrete implementations: `chroma_store.py`, `llm_client.py`, `file_knowledge_repo.py`, `memory_session.py`, `sqlite_session.py`, `event_sinks.py`. |
| Agents | `agents/` | LLM agent stubs (all empty, V2). |
| Knowledge | `knowledge/` | Knowledge graph, terminology, misconception mapper, prompt builder, term expander. |
| RAG | `rag/` | PDF→Markdown→Chunk→Vector Store→Retrieval pipeline. |
| Data | `data/` | Static JSON/CSV files (terms, questions, socratic chains, feynman rubrics, knowledge graph). |
| Database | `database/` | Relational DB stubs. |

### SSE Stream Event Protocol

Designed 2026-07-11. Fine-grained streaming events for real-time progress during API calls.

**StreamEvent** (`schemas/events.py`) — unified event model:
- `event_id` (evt_0008), `run_id` (run_abc123), `session_id`, `sequence` (monotonic), `event` (dot notation), `stage`, `payload`
- 10 event types: `run.started`, `retrieval.started`, `retrieval.source_found`, `retrieval.completed`, `generation.started`, `generation.delta`, `generation.section_completed`, `workflow.stage_changed`, `run.completed`, `run.failed`
- `to_sse()` → `text/event-stream` wire format with `event:` / `id:` / `data:` lines
- **EventEmitter** — factory class with auto-incrementing `sequence`, one per run

See `api/sse.py` for FastAPI integration helpers (`sse_stream()`, `create_emitter()`).

### EventSink Protocol

Unified event output — Service/Agent layers don't know whether downstream is Streamlit, SSE queue, or null.

Protocol in `schemas/event_sink.py`:
- `EventSink` (Protocol) — `async emit(event: StreamEvent) -> None`
- `NullEventSink` — silent discard (batch/testing)
- Any object with `async emit()` satisfies the protocol (duck typing)

Implementations in `infrastructure/event_sinks.py`:
- `StreamlitEventSink(placeholder)` — renders `generation.delta` into `st.empty()`
- `RunStoreEventSink(store, run_id)` — buffers events for SSE replay
- `QueueEventSink(queue)` — pushes into `asyncio.Queue` for backpressure control
- `CallbackEventSink(callback)` — forwards to sync/async callbacks

### Service Layer — Class-based DI

`QAService` (`services/qa_service.py`) refactored to class with constructor injection:
```python
class QAService:
    def __init__(self, rag_repo: RAGRepository, knowledge_repo: KnowledgeRepository,
                 llm_client: LLMClient | None = None):
        ...
    async def answer(self, request: QARequest, *, sink: EventSink | None = None) -> QAResult
    async def answer_stream(self, request: QARequest) -> AsyncIterator[StreamEvent]
```
- All dependencies injected via `__init__`, no hard-coded imports
- `sink` parameter accepts any EventSink implementation
- Old `answer_question(user_question)` kept for backward compat (delegates internally)
- `create_qa_service()` factory for Streamlit / non-DI contexts

### REST API Boundaries

API designed around **resources + operations**, not page names. All endpoints that touch business logic call the **same `services/` functions as Streamlit pages** — zero duplicated implementation.

```
# Sessions & Runs (infrastructure)
POST   /api/v1/sessions/                          Create session            [✅ implemented]
GET    /api/v1/sessions/{id}                      Get session state         [✅ implemented]
DELETE /api/v1/sessions/{id}                      Delete session            [✅ implemented]
GET    /api/v1/runs/{id}                          Get run result            [✅ implemented]
GET    /api/v1/runs/{id}/events                   SSE event stream          [✅ implemented]
DELETE /api/v1/runs/{id}                          Delete run                [✅ implemented]

# Business endpoints (all → services/, same as Streamlit)
POST   /api/v1/sessions/{id}/qa-runs              Create QA run             [✅ → qa_service.QAService.answer()]
POST   /api/v1/sessions/{id}/diagnoses            Submit diagnosis          [✅ → diagnosis_service.submit_answer()]
POST   /api/v1/sessions/{id}/socratic/answers     Submit socratic answer    [✅ → socratic_service.judge_answer()]
POST   /api/v1/sessions/{id}/feynman-evaluations  Submit feynman evaluation [✅ → feynman_service.evaluate()]
POST   /api/v1/sessions/{id}/recommendations      Get learning path         [✅ → recommendation_service.generate_learning_path()]
GET    /api/v1/sessions/{id}/knowledge-graph      Get knowledge graph       [✅ implemented]

# Supplementary endpoints
GET    /api/v1/questions/{id}                     Get question (display)     [✅ → diagnosis_service.get_question_for_page()]
GET    /api/v1/questions                          List all questions         [✅ → diagnosis_service.get_all_questions()]
GET    /api/v1/socratic-chains/{id}               Get socratic chain         [✅ → socratic_service.load_socratic_chain()]
GET    /api/v1/feynman-rubrics/{id}               Get feynman rubric         [✅ → feynman_service.load_feynman_rubric()]
GET    /api/v1/feynman-rubrics                    List all rubrics           [✅ implemented]
GET    /api/v1/knowledge-units                    List knowledge units       [✅ → recommendation_service.KNOWLEDGE_UNITS]
```

**Pattern**: `POST create task → GET SSE events` (not query-string streaming). Router files in `api/routers/` — one per resource. `api/dependencies.py` provides FastAPI `Depends()` factories. `api/run_store.py` buffers events for SSE replay with TTL cleanup.

**Dual-entry-point guarantee**: Every business endpoint imports directly from `services/` — the exact same module and function that the corresponding Streamlit page calls. There is no FastAPI-specific reimplementation of any QA, diagnosis, socratic, feynman, or recommendation logic.

### Frontend State Architecture

Two-layer state separation (see `frontend/README.md`):
1. **Server state** → TanStack Query / Vue Query — LearningSession, QAResult, etc. Backend is authority.
2. **Client UI state** → 4 lightweight Zustand/Pinia stores: `uiStore`, `streamStore`, `userStore`, `learningStore` (ID pointers only, no data duplication).

Never copy LearningSession into UI store — TanStack Query cache is the single source.

### LearningSession — canonical session model

`schemas/learning_session.py` defines `LearningSession` (Pydantic BaseModel), the single source of truth for learning-loop state. `st.session_state["learning_session"]` is a plain dict cache only.

```python
# Streamlit page usage:
from utils.state import init_session_state, get_learning_session, save_learning_session
init_session_state()
session = get_learning_session()           # -> LearningSession
result = qa_service.answer_question(req)
session.qa_result = result.model_dump()
session.current_stage = LearningStage.DIAGNOSIS
save_learning_session(session)             # syncs legacy flat keys automatically

# Future FastAPI usage:
session = LearningSession(**await db.load(session_id))
result = qa_service.answer_question(req)
session.qa_result = result.model_dump()
await db.save(session.model_dump())
```

### State machine with guard conditions

`workflows/learning_loop.py` — the backend enforces allowed transitions:

| From | To | Guard |
|------|----|-------|
| QA | DIAGNOSIS | (unconditional) |
| DIAGNOSIS | FEYNMAN | `diagnosis_passed` (is_correct=True) |
| DIAGNOSIS | SOCRATIC | `diagnosis_failed` (is_correct=False) |
| SOCRATIC | FEYNMAN | (unconditional) |
| FEYNMAN | RECOMMENDATION | `feynman_pass` (score >= 60) |
| FEYNMAN | SOCRATIC | `feynman_weak` (score < 60) |
| RECOMMENDATION | COMPLETED | (unconditional) |
| Any | QA | (unconditional restart) |

Even if the frontend sends requests out of order, the state machine rejects them:
```python
machine = LearningLoopMachine.from_session(session)
if not machine.can_advance_to(LearningStage.FEYNMAN):
    raise HTTPException(409, "Invalid transition")
result = machine.complete_diagnosis(is_correct=True)
# result.to_stage == FEYNMAN (skips Socratic)
```

### Pydantic schemas — unified data protocol

All cross-layer types are in `schemas/`, split by domain. Every field has a `description` for auto-generated OpenAPI docs. Frontend TypeScript types can be generated from the OpenAPI schema.

Page filenames use underscores only (no spaces, no apostrophes): `1_Smart_Answering.py`, `2_Error_Diagnosis.py`, etc. The `utils/state.py` `PAGES` dict maps short keys to these paths for `go_to()`.

## RAG Pipeline (rag/)

The canonical RAG implementation. Supersedes the older `knowledge/indexing/` and `knowledge/retrievers/` (kept for reference, not used by any active code).

### Pipeline scripts

| Script | Role |
|--------|------|
| `rag/pdf_parser.py` | PDF → Markdown via **Marker** (visual-AI parser). Handles dual-column layouts, formulas→LaTeX, tables→Markdown, image extraction. Output to `data/processed/markdown/{lang}/{doc_id}.md`. |
| `rag/chunker.py` | Markdown → semantic chunks via LangChain **MarkdownHeaderTextSplitter** (H1/H2/H3). Falls back to RecursiveCharacterTextSplitter for oversized sections. |
| `rag/prepare_chunks.py` | Full pipeline orchestrator. Flags: `--pdf-only`, `--chunk-only`. `pdf_parser` is lazily imported so `--chunk-only` works without Marker installed locally. |
| `rag/build_vector_store.py` | Chunks → ChromaDB. `--backend dashscope` (推荐) 使用 API，`--backend local` 使用 BGE-m3。Collections: `materials_zh`, `materials_en`, `materials_images`。存储到 `C:\chroma_data\v2_{zh,en,images}/`。 |
| `rag/check_chunks.py` | Quality stats: empty chunks, length distribution, metadata completeness, headers coverage, per-doc counts. Run before building vector store. |
| `rag/bilingual_retriever.py` | `BilingualRetriever` class: DashScope API 优先（零本地内存），BGE-m3 惰性 fallback。术语扩展 + 双语检索 + 图片搜索。惰性 PersistentClient 避免 Windows 文件锁冲突。 |
| `rag/dashscope_embedder.py` | **NEW** — DashScope text-embedding-v4 API 封装（OpenAI 兼容接口）。API Key 从 `DASHSCOPE_API_KEY` 环境变量读取，不硬编码。 |
| `rag/image_captioner.py` | **Executed** — Qwen-VL-Max via DashScope OpenAI-compatible API → structured chart descriptions. Filters to `Figure`-named images only, no quantity limit. |

### Pipeline execution results (2026-07-10)

| Step | Status | Details |
|------|--------|---------|
| PDF → Markdown | ✅ (5090 server) | zh: 1.74MB, 813 figures; en: 3.13MB, 823 figures |
| Image Captioning | ✅ (local, Qwen-VL-Max) | 935 figures captioned (508 zh + 427 en), ~¥5-8 cost |
| Markdown → Chunks | ✅ | zh: 1523 chunks, en: 3234 chunks |
| Vector Store | ✅ | 3 ChromaDB collections, 5692 total chunks, ~70MB |

**Vector store**: stored at `C:\chroma_data\v2_{zh,en,images}/` (pure ASCII path, Cloudflare HNSW compatible). Override with `CHROMA_DATA_DIR` env var. Old `vector_store/` directory deprecated.

### Output directory structure

```
data/processed/
  markdown/           ← Marker output (already reviewed)
    zh/材料科学基础_清华.md
    en/Materials Science...第十版.md
  images/             ← extracted figures (1636 total)
    zh/材料科学基础_清华/  (813 jpeg)
    en/Materials Science.../  (823 jpeg)
  chunks/             ← semantic chunks (JSONL)
    zh_chunks.jsonl   (1523 chunks)
    en_chunks.jsonl   (3234 chunks)
    image_captions.jsonl  (935 chunks, chunk_type="image")

C:/chroma_data/
  v2_zh/              ← ChromaDB: materials_zh (1523 chunks)
  v2_en/              ← ChromaDB: materials_en (3234 chunks)
  v2_images/          ← ChromaDB: materials_images (935 chunks)
  # 可通过 CHROMA_DATA_DIR 环境变量自定义路径
  # 旧 vector_store/ 目录已废弃（含中文路径，HNSW 不兼容）
```

### Chunk format

Text chunks:
```json
{
  "chunk_id": "zh_{doc_id}_c1",
  "doc_id": "...",
  "file_name": "....pdf",
  "language": "zh",
  "chapter": "第一章 ...",
  "section": "1.1 ...",
  "headers": {"h1": "...", "h2": "...", "h3": "..."},
  "chunk_index": 1,
  "chunk_size": 850,
  "text": "...",
  "image_captions": []
}
```

Image caption chunks (fields differ from text chunks):
```json
{
  "chunk_id": "zh_材料科学基础_清华__page_103_Figure_2",
  "chunk_type": "image",
  "text": "【图表类型】晶体结构示意图\n【描述】...",
  "image_path": "data/processed/images/zh/...",
  "image_name": "_page_103_Figure_2.jpeg",
  "related_terms": ["HCP", "BCC", "晶胞"],
  "language": "zh",
  "doc_id": "...",
  "file_name": "..."
}
```

### ChromaDB Windows 兼容性问题

ChromaDB 1.5.9 的 Rust HNSW 后端在 Windows 上有两个已知 bug，已在 `bilingual_retriever.py` 中规避：

1. **中文路径 bug**：绝对路径含非 ASCII 字符（如 `E:\AI+教学\...`）时，HNSW 索引读取失败。**修复**：向量库默认存储到 `C:\chroma_data\`（纯 ASCII 路径），可通过 `CHROMA_DATA_DIR` 环境变量覆盖。注意：相对路径**不能**解决此问题（ChromaDB 内部会解析为绝对路径）。

2. **多客户端冲突**：同时持有多个 `PersistentClient` 实例会导致 compactor 文件锁冲突。**修复**：惰性单例模式——`_get_collection()` 每次只打开一个客户端，用完立即 `del` 释放，用 `get_collection`（非 `get_or_create_collection`）避免触发 compactor。

### Embedding 后端（2026-07-11 更新）

为减少本地内存占用（BGE-M3 加载后 ~2GB），已迁移至 DashScope API：

| 组件 | 主后端 | Fallback | 说明 |
|------|--------|----------|------|
| 向量库构建 | DashScope text-embedding-v4 | BGE-M3（`--backend local`） | `python -m rag.build_vector_store --backend dashscope` |
| 查询向量化 | DashScope API（优先） | BGE-M3 本地模型 | `bilingual_retriever.py` 惰性加载，网络故障自动切换 |
| Embedding 封装 | `rag/dashscope_embedder.py` | — | OpenAI 兼容接口，batch_size=5（长文本限制） |

DashScope text-embedding-v4：1024 维（与 BGE-M3 一致），通过现有 `DASHSCOPE_API_KEY` 调用，成本 ~¥0.0005/千 token。向量库需用 `--backend dashscope` 重建（embedding 空间不兼容）。

### Server requirements

Marker PDF conversion needs **8GB+ RAM** and a GPU with CUDA support. Successfully tested on RTX 5090 (32GB) with PyTorch 2.11.0+cu128, CUDA 12.8. Downloads ~3.5GB of models on first run (Surya OCR, layout, recognition, detection, table recognition). Use `HF_ENDPOINT=https://hf-mirror.com` in China.

Conversion benchmarks (5090):
- 中文 PDF (71.5MB, 70 pages): ~15 min, 813 images extracted
- 英文 PDF (15MB, ~900 pages): ~20 min, 823 images extracted

### Before running: 5 manual checks on Markdown output

1. Are chapter titles recognized as `#` / `##` / `###`? → Use `python check_headings.py` to extract and review.
2. Is body text order correct?
3. Are tables severely garbled?
4. Are formulas at least readable?
5. Are figures saved, and can they be traced in the Markdown?

**Quality assessment** (2026-07-09):
- 🇨🇳 Chinese (`材料科学基础_清华.md`): **Excellent** — clear H1→H2→H3 hierarchy matching the textbook TOC.
- 🇬🇧 English (`Materials Science...md`): **Acceptable** — chapters detected but mostly flattened to `##`, with some formula/body-text noise mislabeled as headings. Chunks may be larger/coarser than Chinese.

**Marker compatibility fix**: Marker ≥1.10 returns PIL `Image` objects in `rendered.images`, not bytes. `rag/pdf_parser.py` uses `BytesIO` for compatibility with both old and new versions.

### Healthy chunk stats (achieved)

- Empty chunks: 0 ✅
- Avg length: zh 695 / en 980 chars ✅
- Max length: zh 1000 / en 1200 ✅
- Metadata missing: 0 ✅
- Headers coverage: zh 99.9% / en 100% ✅

### Image captioning details

- **Model**: Qwen-VL-Max (via DashScope OpenAI-compatible API, `https://dashscope.aliyuncs.com/compatible-mode/v1`)
- **API key**: configured in `.env` as `DASHSCOPE_API_KEY`
- **Filter**: only files with `Figure`/`figure`/`fig` in name (filtered 701 non-Figure images: logos, decorations, etc.)
- **Prompt**: structured Chinese output with chart type, description, and key terms
- **Cost**: ~¥5-8 for all 935 figures
- **Caption format**: `【图表类型】... 【描述】... 【关键术语】...`

## Implementation status

### RAG Pipeline (complete)
- ✅ `rag/` — complete pipeline: PDF→Markdown→image captioning→chunks→vector store→retrieval
- ✅ `services/rag_service.py` — retrieval service layer wrapping `BilingualRetriever`
- ✅ `knowledge/rag_retriever.py` — thin delegation to `services/rag_service` for backward compatibility
- ✅ `knowledge/term_expander.py` — bilingual query expansion (zh↔en term matching)
- ✅ `knowledge/prompt_builder.py` — **`build_constrained_qa_prompt()`**: enforces 4 data source boundaries (RAG=事实依据, graph=因果链, terms.csv=术语标准, questions.json=自测题)
- ✅ `knowledge/knowledge_graph.py` — load/query knowledge graph, `match_chain()` for question→chain matching
- ✅ `knowledge/terminology.py` — bilingual term search from `data/terms.csv`
- ✅ `knowledge/misconception_mapper.py` — load questions, diagnose answers against `data/questions.json`

### Service Layer (complete — LLM-ready interfaces)
- ✅ `services/qa_service.py` — **`answer_question()`**: unified entry, combines 4 data sources, returns structured dict with 11 fields (question, chain_id, short_answer, principle, causal_chain, key_terms, misconceptions, self_test, sources, prompt, retrieval_debug). `short_answer`/`principle` currently use graph summary as placeholder.
- ✅ `services/diagnosis_service.py` — **`submit_answer()`**: returns `diagnosis_result` with `misconception_id` (M_Q001_A format), `missing_concepts`, `recommended_chain_id`, `recommended_socratic_id`
- ✅ `services/socratic_service.py` — **`judge_answer()`**: keyword-based answer quality assessment, returns `{step_id, student_answer_quality, covered_points, missing_points, action, response}`. Actions: advance/hint/retry/simplify/complete. LLM-ready interface.
- ✅ `services/feynman_service.py` — **`evaluate()`**: 6-point checklist keyword matching → 5-dimension scoring (concept_accuracy:18, causal_completeness:20, term_accuracy:14, clarity:16, misconception_control:10, total:78). Generates `next_question` from first missing point.
- ✅ `services/recommendation_service.py` — **`generate_learning_path()`**: aggregates weak points from 3 sources (diagnosis + socratic + feynman), maps to knowledge units (K001-K004) with prerequisite topological sort. Returns `{current_level, weak_points, recommended_steps}`.
- ✅ `services/profile_service.py` — stub (not yet needed for V1)

### Frontend (5 learning-loop pages functional)
- ✅ `pages/1_Smart_Answering.py` — chat input → `answer_question()` → fixed 7-section output (简明回答/原理/因果链/术语/教材依据/误区/自测题). Writes `last_answer`, `current_knowledge_id`, `current_chain_id`, `current_question_id` to session_state.
- ✅ `pages/2_Error_Diagnosis.py` — reads `current_question_id` from session_state, shows question + options, calls `submit_answer()`, renders diagnosis with misconception/missing_concepts/remedial_path. Writes `last_diagnosis`, `current_socratic_id`.
- ✅ `pages/3_Socratic_Guidance.py` — reads `current_socratic_id`, loads S001 chain (6 steps), keyword-based `judge_answer()` per step, progress bar. On complete: writes `last_socratic_result`, `current_feynman_id`.
- ✅ `pages/4_Feynman_Evaluation.py` — reads `current_feynman_id`, text area for explanation, calls `evaluate()`, 5-dimension progress bars (🟢🟡🔴), covered/missing points, reference example. Writes `last_feynman_result`.
- ✅ `pages/6_Learning_Path_Recommendation.py` — aggregates 3 sources → `generate_learning_path()`, shows current_level, weak points with source tracing, recommended_steps in prerequisite order.
- ✅ `pages/5_Knowledge_Graph.py` — stub (graph visualization TODO)
- ✅ `pages/7_Debug.py` — knowledge base debugging dashboard
- ✅ `pages/8_RAG_Debug.py` — RAG retrieval debug page
- ✅ `pages/9_Dataset_Review.py` — data production review page (candidate list + evidence panel + approve/reject)
- ✅ `utils/state.py` — shared session state init (`last_user_question`, `last_answer`, `last_qa_result`, `last_diagnosis`, `last_socratic_result`, `last_feynman_result`, `last_learning_path`) and page navigation

### Learning Loop (fully connected)
```
1_Smart_Answering ──→ 2_Error_Diagnosis ──→ 3_Socratic_Guidance ──→ 4_Feynman ──→ 6_Learning_Path
     │ K001,C001,Q001      │ Q001→M_Q001_A→S001   │ S001(6步)→F001      │ F001(5维评分)   │ 聚合3源→排序
     └─────────────────────────────────────────────────────────────────────────────────────────┘
                                    session_state 接力传递上下文
```

### Dual-entry-point architecture (2026-07-25)

All 5 business capabilities are exposed through **two entry points sharing the same `services/` layer**:

```
Streamlit pages/          FastAPI api/routers/
     │                         │
     └─────────┬───────────────┘
               │  (same function calls)
               ▼
        services/*.py
               │
               ▼
    knowledge/ + rag/ + repositories/
```

**Verification**: Zero `import streamlit` in `services/`, `workflows/`, `agents/`, `rag/`, `knowledge/`, `repositories/`, `schemas/`, `infrastructure/`. Streamlit exists only in `pages/` + `app.py` + `utils/state.py`.

### Agent Layer (2026-07-31)

**Constrained agents** — each agent has a single responsibility, receives bounded resources (no free tool-calling), and returns structured results with evidence + reasoning trace.

#### Architecture

```
SERVICES (thin orchestrators)
  → gather resources → build AgentContext → call agent.run(ctx) → AgentResult
  → map AgentResult → ServiceResult[DomainResult]
  → V1 keyword fallback when LLM unavailable

AGENTS (constrained LLM calls)
  → receive AgentContext (bounded data) → build specialized prompt
  → call LLM via infrastructure/llm_client.py → parse structured JSON output
  → NEVER touch Streamlit, NEVER decide stage transitions
```

#### Five agents

| Agent | File | Resources | Replaces |
|-------|------|-----------|----------|
| **QAAgent** | `agents/qa_agent.py` | RAG chunks, causal chain, terms, questions | Placeholder short_answer/principle in QAService |
| **DiagnosisAgent** | `agents/diagnosis_agent.py` | Question data, student answer, misconception DB | Enriches mapper output with LLM causal reasoning |
| **SocraticAgent** | `agents/socratic_agent.py` | Socratic step, student answer, attempt count | `judge_answer()` keyword matching |
| **FeynmanAgent** | `agents/feynman_agent.py` | Rubric checklist, student explanation | `evaluate()` keyword matching; adds `incorrect_points` detection |
| **GraphReasoningAgent** | `agents/graph_reasoning_agent.py` | Knowledge graph (nodes+edges), weak points | Keyword-based unit mapping + prerequisite sort |

#### Unified interface

```python
class BaseAgent(Protocol):
    async def run(self, context: AgentContext) -> AgentResult:
        ...

# AgentContext: session_id, student_input, resources (AgentResource), metadata
# AgentResult: content, structured_data, evidence (AgentEvidence), confidence, trace (AgentTrace)
```

All types in `schemas/agent.py`. Agents follow `EventSink` Protocol pattern.

#### Shared helpers (`agents/base.py`)

- `_parse_structured_output()` — extract JSON from LLM response (3 fallback strategies)
- `_build_system_prompt()` — assemble [ROLE] [CONSTRAINTS] [OUTPUT FORMAT] sections
- `_extract_evidence()` — cross-reference LLM claims with provided chunks
- `_call_llm()` — wrap sync `llm_client.chat()` with `asyncio.to_thread`

#### Integration with services

All 5 services wired with V1 fallback everywhere:
- `services/qa_service.py` — calls QAAgent when `self.llm` available
- `services/diagnosis_service.py` — `submit_answer(llm_client=...)` optional parameter
- `services/socratic_service.py` — `judge_answer(llm_client=...)` optional parameter
- `services/feynman_service.py` — `evaluate(llm_client=...)` optional parameter
- `services/recommendation_service.py` — `generate_learning_path(llm_client=...)` optional parameter

LLM unavailable → silent fallback to existing V1 keyword engines. No breaking changes.

#### Key design rules

1. Agents are stateless — receive context, return results, no side effects
2. Services remain the orchestrators — gather resources, call agents, map results
3. State machine is unchanged — agents never call `LearningLoopMachine` methods
4. `AgentEvidence` always populated — captures which chunks/nodes were used (even in V1 mode)
5. `AgentTrace` for competition defense — step-by-step reasoning in `reasoning_steps`

### Remaining stubs
- `services/profile_service.py`
- `database/db.py`, `database/models.py`
- `pages/5_Knowledge_Graph.py` (interactive graph visualization)

**Superseded (kept for reference, not used)**:
- `knowledge/indexing/` — old pymupdf-based PDF parsing + character chunking
- `knowledge/retrievers/` — old separate zh/en retrievers with MiniLM embeddings

## Key patterns

### Data file access

```python
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "data" / "some_file.json"
```

### Service → Page contract

Services return plain dicts. Pages read those dicts and render Streamlit widgets. Services never import Streamlit.

**Unified response structure** — all service functions return structured dicts with fixed keys. Pages render dict fields directly, never parse free-form LLM text.

**Four data source constraint** — `prompt_builder.py` enforces clear boundaries:
| Source | Role | Forbidden |
|--------|------|-----------|
| Textbook RAG | Facts: definitions, principles, transformations, properties | — |
| Knowledge graph | Causal chain path only | Inventing new nodes |
| terms.csv | Standardized terminology translations | LLM inventing translations |
| questions.json | Self-test question matching | LLM creating ad-hoc questions |

### Session state chain (learning loop)

Five pages pass context through `session_state` with fixed key names:

```python
# Page 1 → Page 2
st.session_state["last_answer"] = result           # full structured dict
st.session_state["current_knowledge_id"] = "K001"
st.session_state["current_chain_id"] = "C001"
st.session_state["current_question_id"] = "Q001"

# Page 2 → Page 3
st.session_state["last_diagnosis"] = diagnosis_result
st.session_state["current_socratic_id"] = "S001"

# Page 3 → Page 4
st.session_state["last_socratic_result"] = {...}
st.session_state["current_feynman_id"] = "F001"

# Page 4 → Page 6
st.session_state["last_feynman_result"] = {...}
```

All keys initialized in `utils/state.py` `DEFAULT_STATE`. Pages read from `session_state`, never hardcode IDs.

### V1 rule engines (LLM-ready swap points)

Three services use keyword-based rule engines with interfaces designed for drop-in LLM replacement:

| Service | Function | V1 Engine | LLM Swap Point |
|---------|----------|-----------|----------------|
| `socratic_service` | `judge_answer()` | Keyword match vs `expected_keywords` → action decision | Replace with LLM call, keep return schema |
| `feynman_service` | `evaluate()` | Checklist keyword match → dimension scores | Replace scoring, keep 5-dimension schema |
| `recommendation_service` | `generate_learning_path()` | Weak point → knowledge unit keyword mapping + prerequisite sort | Replace mapping, keep `recommended_steps` schema |

## Static data files (V1 scope)

- `data/knowledge_graph.json` — 8 nodes, 7 edges, 1 causal chain (C001: quenching → hardness)
- `data/questions.json` — 10 questions with 4 options, answer explanation, and per-wrong-option diagnosis
- `data/terms.csv` — 10 bilingual terms
- `data/socratic.json` — 1 socratic chain with 6 steps (linear, no branches)
- `data/feynman.json` — 10 evaluation rubrics
- Textbook PDFs: `data/textbooks/zh/材料科学基础_清华.pdf`, `data/textbooks/en/Materials Science and Engineering...pdf` (NOT in git)

## Data production & review system (2026-07-27)

Expands question bank, Socratic chains, and Feynman rubrics from ~10 items each to teaching-scale datasets. Fully evidence-grounded — all generation constrained by textbook RAG chunks, KG nodes, and terms.csv.

### Pipeline overview

```
KG nodes/causal chains → EvidencePackage (RAG chunks + KG + terms)
  → GenerationBlueprints (control type/difficulty distribution)
  → Generator Agent (LLM, constrained prompt) → candidate data
  → Critic Agent (separate LLM call, review only)
  → Deterministic validators (5 checks, no LLM)
  → Quality scoring (6 dimensions, 0-100)
  → Human review (Streamlit page 9_Dataset_Review)
  → Publish to data/published/v{version}/
```

### Four data categories

| Category | Description | Key constraint |
|----------|-------------|----------------|
| **QA items** | 6 question types (definition/causal/comparison/conditional/reverse/application) + 4 options + misconception diagnosis per wrong option | source_refs must point to real ChromaDB chunks; graph_path must use valid KG node IDs |
| **Student answer samples** | 5-6 quality levels per question (completely_wrong → partial → terms_right_logic_wrong → mostly_correct → high_quality → excellent_transfer) | For testing diagnosis/Socratic/Feynman agents |
| **Socratic chains** | Branched teaching state graphs (correct→advance, partial→hint, wrong→remedial) | Each step maps to one KG node; must not leak final answer |
| **Feynman tasks + responses** | Task rubric (mandatory_points + forbidden_claims + checklist) + 5-tier student responses | For testing Feynman scoring stability |

### Key design rules

1. **Generator and Critic are separate agents** — never let the same LLM call generate and self-review
2. **EvidencePackage is read-only** — generators cannot use facts, nodes, or terms outside the package
3. **Quality score thresholds**: <70 reject, 70-84 careful human review, >=85 normal review. Fatal errors (no evidence / graph conflict) → reject regardless of score.
4. **Gold eval set isolation**: `data/eval_gold/` is human-created only, never seen by generator agents
5. **Full provenance**: every item tracks `created_by`, `generator_prompt_version`, `critic_model`, `reviewer`, `dataset_version`

### New modules

| Layer | Files | Purpose |
|-------|-------|---------|
| schemas/ | `dataset_item.py`, `generation_blueprint.py`, `validation_report.py`, `dataset_review.py` | All data production Pydantic models |
| validators/ | `schema_validator.py`, `evidence_validator.py`, `graph_validator.py`, `terminology_validator.py`, `duplicate_validator.py` | 5 deterministic checks (no LLM) |
| agents/ | `dataset_generator_agent.py`, `dataset_critic_agent.py` | LLM-powered Generator + Critic |
| services/ | `dataset_expansion_service.py` | Pipeline orchestrator (DI constructor) |
| repositories/ | `dataset_repo.py` | Dataset repository ABC |
| infrastructure/ | `jsonl_dataset_repo.py`, `dataset_version_store.py` | JSONL implementation + version management |
| pages/ | `9_Dataset_Review.py` | Streamlit human review page |
| scripts/ | `expand_qa_dataset.py`, `expand_socratic_dataset.py`, `expand_feynman_dataset.py`, `run_validation.py`, `publish_dataset.py` | CLI entry points |

### CLI usage

```bash
python scripts/expand_qa_dataset.py --knowledge-ids K_QUENCHING,K_MARTENSITE --count 20
python scripts/run_validation.py --type all
python scripts/publish_dataset.py --type qa --approved-only --version 2026.08.1
```

### Data lifecycle

```
candidate → auto_validated → needs_review → approved → published → deprecated
                             ↓
                          rejected (kept for dedup reference)
```

### Directory layout for generated data

```
data/
  candidates/{qa,socratic,feynman}_candidates.jsonl   # generated, NOT in git
  reviewed/   # reviewed items, NOT in git
  rejected/   # rejected items (for dedup), NOT in git
  published/v{version}/{type}.json   # published datasets, NOT in git
  eval_gold/  # human-created gold standard, NOT in git (never expose to generators)
```

## LLM configuration

Uses `.env` for API keys (Anthropic, DeepSeek, OpenAI). Default model set to `claude-sonnet-4-6`. The RAG pipeline is implemented end-to-end (PDF parse → chunk → vector store → retrieve → prompt build) but the final LLM call in `qa_service.py` is not yet wired — it currently returns the assembled prompt alongside mock answer text.

## Git conventions

Commits follow Conventional Commits with Chinese descriptions:
```
feat: 实现错题诊断功能
fix: 修复RAG检索空结果
docs: 更新README
refactor: 重构项目目录结构
chore: 初始化项目结构
```

The main branch is `main`. The working branch is `master`.
