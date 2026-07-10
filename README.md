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

## 技术架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        页面展示层 (pages/)                        │
│   Streamlit 多页面应用：答疑 / 错题诊断 / 苏格拉底引导 /           │
│   费曼评价 / 知识图谱 / 学习路径推荐 / RAG Debug                   │
├─────────────────────────────────────────────────────────────────┤
│                        业务服务层 (services/)                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ rag      │ │ 答疑服务  │ │ 诊断服务  │ │ 苏格拉底  │ │ 费曼评价  │ │
│  │ service  │ │ qa       │ │ diagnosis│ │ socratic │ │ feynman  │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
├─────────────────────────────────────────────────────────────────┤
│                     RAG 管线 (rag/)                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ PDF→MD   │ │ 语义分块  │ │ BGE-m3   │ │ 双语检索  │ │ 图表      │ │
│  │ Marker   │ │ H1/H2/H3 │ │ 向量化    │ │ +术语扩展 │ │ Caption   │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
├─────────────────────────────────────────────────────────────────┤
│                        AI 推理层 (agents/)                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ 答疑      │ │ 错题诊断  │ │ 苏格拉底  │ │ 费曼      │ │ 图谱推理  │ │
│  │ Agent    │ │ Agent    │ │ Agent    │ │ Agent    │ │ Agent    │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
├─────────────────────────────────────────────────────────────────┤
│                       知识增强层 (knowledge/)                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ RAG      │ │ 知识图谱  │ │ 术语对齐  │ │ 术语扩展  │ │ Prompt   │ │
│  │ retriever│ │ graph    │ │ terminology│ │ expander │ │ builder  │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
├─────────────────────────────────────────────────────────────────┤
│                      数据 & 存储层                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐             │
│  │ data/    │ │ database/│ │ vector_  │ │ configs/ │             │
│  │ 教材/题库│ │ 学生记录  │ │ store/   │ │ 模型配置  │             │
│  │ 知识图谱 │ │          │ │ ChromaDB │ │          │             │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 项目结构

```
CaiZhi-Agent/
│
├── app.py                         # Streamlit 主入口
│
├── pages/                         # 页面展示层 —— 纯 UI，不含业务逻辑
│   ├── 1_Smart_Answering.py       # 智能答疑
│   ├── 2_Error_Diagnosis.py       # 错题诊断
│   ├── 3_Socratic_Guidance.py     # 苏格拉底引导
│   ├── 4_Feynman_Evaluation.py    # 费曼评价
│   ├── 5_Knowledge_Graph.py       # 知识图谱（stub）
│   ├── 6_Learning_Path_Recommendation.py  # 学习路径推荐（stub）
│   ├── 7_Debug.py                 # 知识库调试
│   └── 8_RAG_Debug.py             # RAG 检索调试（✅ 已实现）
│
├── services/                      # 业务服务层
│   ├── rag_service.py             # ✅ RAG 检索服务封装
│   ├── qa_service.py              # ✅ 答疑服务（LLM待接入）
│   ├── diagnosis_service.py       # ✅ 错题诊断服务
│   ├── socratic_service.py        # stub
│   ├── feynman_service.py         # stub
│   ├── profile_service.py         # stub
│   └── recommendation_service.py  # stub
│
├── rag/                           # ✅ RAG 管线（PDF→Markdown→Chunk→向量库→检索）
│   ├── pdf_parser.py              #   PDF→Markdown（Marker 视觉AI解析）
│   ├── chunker.py                 #   语义分块（MarkdownHeaderTextSplitter）
│   ├── prepare_chunks.py          #   全流程编排（--pdf-only / --chunk-only）
│   ├── build_vector_store.py      #   ChromaDB + BGE-m3 向量化
│   ├── bilingual_retriever.py     #   双语检索 + 术语扩展 + 图片字段透传
│   ├── check_chunks.py            #   Chunk 质量统计
│   ├── image_captioner.py         #   图表 Caption（Qwen-VL-Max）
│   ├── fix_metadata.py            #   修复向量库 metadata（免重编码）
│   └── enrich_images.py           #   图片索引补全（page/nearby_header/caption_status）
│
├── agents/                        # AI 推理层 —— 全部为 stub
│   ├── qa_agent.py
│   ├── mistake_diagnosis_agent.py
│   ├── socratic_agent.py
│   ├── feynman_agent.py
│   └── graph_reasoning_agent.py
│
├── knowledge/                     # 知识增强层
│   ├── rag_retriever.py           #   检索入口（委托到 services/rag_service）
│   ├── knowledge_graph.py         # ✅ 知识图谱查询
│   ├── terminology.py             # ✅ 术语查询
│   ├── term_expander.py           # ✅ 查询术语扩展（中↔英）
│   ├── misconception_mapper.py    # ✅ 错题-误区映射
│   ├── prompt_builder.py          # ✅ RAG Prompt 组装
│   ├── retrievers/                # ⚠️ 旧版检索器（已被 rag/ 替代，保留参考）
│   └── indexing/                  # ⚠️ 旧版索引构建（已被 rag/ 替代，保留参考）
│
├── data/                          # 数据
│   ├── textbooks/                 #   教材 PDF（不入库）
│   │   ├── zh/                    #     中文教材
│   │   └── en/                    #     英文教材
│   ├── processed/                 #   RAG 产出（不入库）
│   │   ├── markdown/              #     Marker 输出的 Markdown
│   │   ├── images/                #     提取的图表
│   │   └── chunks/                #     语义分块 JSONL
│   ├── terms.csv                  #   术语表
│   ├── knowledge_graph.json       #   知识图谱
│   ├── questions.json             #   题库
│   ├── socratic.json              #   苏格拉底引导
│   └── feynman.json               #   费曼评价标准
│
├── vector_store/                  # ChromaDB 向量库（不入库，本地生成）
│
├── database/                      # 关系数据库（stub）
├── configs/                       # 配置文件
├── check_headings.py              # 提取 Markdown 标题大纲（质量校验）
├── fix_en_headings.py              # 修复英文教材标题层级 + OCR 噪音
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

### 4. 运行 RAG 管线（⚠️ 需 8GB+ RAM，建议在服务器执行）

```bash
# Step 1: PDF → Markdown（先人工检查 Markdown 质量）
python -m rag.prepare_chunks --pdf-only

# 检查 Markdown 质量 —— 用 check_headings.py 提取大纲
python check_headings.py
# 核验：① 章节标题是否识别为 #/##/###  ② 大纲是否与目录对应

# Step 2: Markdown → 语义 Chunks
python -m rag.prepare_chunks --chunk-only

# Step 3: Chunk 质量检查
python -m rag.check_chunks
# 健康指标：空chunk=0，平均长度 500-1500 字符，最大<6000，metadata缺失=0

# Step 4: 构建向量库
python -m rag.build_vector_store
```

### 5. 启动应用

```bash
streamlit run app.py
```

进入 **RAG Debug** 页（第 8 页）验证检索效果。

---

## V1 实现状态

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
| session_state 体系 | ✅ 已统一 | 清理死 key，统一命名，5 页全链路对齐 |
| 智能答疑 (页 1) | 🔧 框架已有 | Prompt 组装就绪，LLM 调用待接入 |
| 错题诊断 (页 2) | ✅ 已实现 | 完整错题诊断 UI + 后端 |
| 苏格拉底引导 (页 3) | 🔧 框架已有 | |
| 费曼评价 (页 4) | 🔧 框架已有 | |
| 知识图谱 (页 5) | 🔧 stub | |
| 学习路径推荐 (页 6) | 🔧 stub | |
| 调试页面 (页 7) | ✅ 已实现 | 术语表 + 知识图谱数据验证 |
| 知识图谱 `knowledge_graph.py` | ✅ 已实现 | 8 节点 / 7 边 / 1 因果链 |
| 术语检索 `terminology.py` | ✅ 已实现 | 双语术语搜索 |
| 术语扩展 `term_expander.py` | ✅ 已实现 | 查询中英双向术语扩展 |
| Prompt 构建 | ✅ 已实现 | 双语教材 + 图表 + 术语 + 图谱 |
| Agent 层 | ❌ 全部 stub | 5 个 Agent 文件待实现 |

---

**转换结果**（2026-07-09，RTX 5090）：

| 教材 | Markdown | 图片 |
|------|----------|------|
| 🇨🇳 材料科学基础（清华） | 1.74 MB | 813 张 |
| 🇬🇧 Materials Science (Callister 10e) | 3.13 MB | 823 张 |

质量评估：中文标题层级优秀（H1→H2→H3）。英文原始标题偏扁平（多为 H2），通过 `fix_en_headings.py` 修复后：25 个 H1 章、106 个 H2 节、13 个 H3 小节，22 个章节完整对齐。

---

## RAG 技术方案

| 环节 | 技术选型 | 说明 |
|---|---|---|
| PDF 解析 | **Marker** (surya OCR) | 视觉 AI 解析，支持双栏排版/公式→LaTeX/表格→Markdown/图片提取 |
| 文本分块 | **MarkdownHeaderTextSplitter** | 按 H1/H2/H3 语义切分，保留章节 metadata |
| Embedding | **BAAI/bge-m3** | 多语言、8192 token、学术专业词汇理解强 |
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
| Embedding | BGE-m3 |
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
