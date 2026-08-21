# AutoReasearch

> 基于 LangGraph 的多智能体学术研究助手：输入一个研究主题，自动完成 **任务拆解 → 多源文献检索 → PDF 下载与解析 → RAG 向量检索 → 子任务摘要 → 综合报告生成**，全程 SSE 流式输出进度。

## ✨ 特性

- **LangGraph 工作流编排**：`planner → fan_out_tasks → task_pipeline × N（并行）→ synthesizer`，使用 `Send()` 原语实现并行 fan-out，`operator.add` reducer 自动合并多任务结果。
- **多源学术检索**：内置 8 种搜索后端可切换 —— Academic、Google Scholar、arXiv、Perplexity、Tavily、DuckDuckGo、SearXNG、Advanced 聚合。
- **文献分区筛选**：支持 CCF-A/B/C、JCR Q1~Q4、arXiv 分级过滤，可多选组合。
- **PDF 全流程**：自动下载 PDF → PyMuPDF 解析 → ChromaDB 向量化（sentence-transformers）→ 语义检索增强上下文（RAG）。
- **流式摘要**：单任务摘要支持 SSE 流式输出，前端实时渲染；自动剥离 LLM 的 thinking token（`自己的想法` / `等待回复`）。
- **笔记协作**：可选 NoteTool 持久化每个子任务的研究进展，支持跨 Agent 复用 `note_id`。
- **Zotero 集成**：可一键自动导入检索到的文献到 Zotero 文献库。
- **CAMEL 同行评议**：可选 CAMEL Researcher-Reviewer 多轮对话机制对摘要做质量审查。
- **多 LLM 后端**：支持 Ollama、LMStudio 或任何 OpenAI 兼容 API（含远程服务）。

## 🏗 系统架构

```
┌──────────────────────────────────────────────────────────────────┐
│                          FastAPI (main.py)                       │
│  /healthz        /research          /research/stream (SSE)       │
└────────────────────────────────┬─────────────────────────────────┘
                                 │ DeepResearchAgent
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                    LangGraph StateGraph                          │
│                                                                  │
│   ┌─────────┐    Send()    ┌──────────────────┐                  │
│   │ planner │ ─────────▶  │ task_pipeline × N │ (并行 fan-out)   │
│   └─────────┘              └────────┬─────────┘                  │
│                                   ▼                              │
│   ┌─────────────────────────────────────────────────┐            │
│   │ task_pipeline: 搜索 → PDF下载 → RAG索引 → 摘要 │            │
│   └────────────────────────────────┬────────────────┘            │
│                                    ▼  operator.add               │
│                            ┌──────────────┐                      │
│                            │ synthesizer  │  → 持久化 + 报告     │
│                            └──────────────┘                      │
└──────────────────────────────────────────────────────────────────┘
```

## 🧰 技术栈

| 层级 | 技术 |
|---|---|
| 后端 | Python ≥ 3.10、FastAPI、Uvicorn、Pydantic、Loguru |
| 工作流 | LangGraph ≥ 0.4、LangChain-Core |
| LLM | OpenAI SDK（兼容 Ollama / LMStudio / 远程服务） |
| 检索 | Tavily、DuckDuckGo（ddgs）、arxiv、scholarly、OpenAlex、Crossref、Semantic Scholar |
| RAG | ChromaDB、sentence-transformers |
| PDF | PyMuPDF |
| 协议 | MCP（Model Context Protocol）—— Zotero Server、Scholar Server |
| 文献管理 | pyzotero |
| 评议 | camel-ai |
| 前端 | Vue 3 + TypeScript + Vite 6 |

## 📂 项目结构

```
AutoReasearch/
├── backend/
│   ├── pyproject.toml
│   └── src/
│       ├── main.py              # FastAPI 入口：/healthz /research /research/stream
│       ├── agent.py             # DeepResearchAgent：编排 LangGraph
│       ├── config.py            # Configuration + SearchAPI + 环境变量加载
│       ├── models.py           # Pydantic 数据模型（TodoItem 等）
│       ├── prompts.py          # 固定提示词模板
│       ├── graph/
│       │   ├── workflow.py     # build_research_graph()：组装 StateGraph
│       │   ├── state.py        # ResearchState / TaskPipelineInput
│       │   └── nodes.py        # fan_out_tasks / task_pipeline_node / synthesizer_node
│       └── services/
│           ├── planner.py      # PlanningService：任务拆解（JSON/TOOL_CALL/fallback 三层解析）
│           ├── summarizer.py  # SummarizationService：同步 + 流式摘要
│           ├── reporter.py     # ReportingService：最终报告生成
│           ├── rag_engine.py   # RAGEngine：ChromaDB 索引 + 检索
│           ├── pdf_downloader.py
│           ├── pdf_parser.py
│           ├── search.py / academic_search.py / arxiv_search.py ...
│           ├── note_tool.py / notes.py
│           ├── zotero_manager.py
│           ├── camel_review.py
│           ├── venue_filter.py
│           └── mcp/             # MCP 服务器（Zotero / Scholar）
└── frontend/
    ├── package.json
    └── src/
        ├── App.vue
        ├── main.ts
        └── services/api.ts      # SSE 流式解析客户端
```

## 🚀 快速开始

### 1. 克隆

```bash
git clone https://github.com/gugi007/AutoReasearch.git
cd AutoReasearch
```

### 2. 后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -e .
```

### 3. 环境变量

在 `backend/src/` 下创建 `.env`：

```ini
# LLM 后端（三选一）
LLM_PROVIDER=ollama            # ollama | lmstudio | custom
LOCAL_LLM=llama3.2             # Ollama 模型名
# LLM_API_KEY=sk-xxx           # 使用远程 OpenAI 兼容服务时填写
# LLM_BASE_URL=https://api.openai.com/v1
# LLM_MODEL_ID=gpt-4o

# 搜索后端
SEARCH_API=academic            # academic | google_scholar | arxiv | perplexity | tavily | duckduckgo | searxng | advanced
VENUE_TIERS=ccf_a,ccf_b,arxiv  # 逗号分隔，留空表示不筛选

# 研究深度
MAX_WEB_RESEARCH_LOOPS=3
PAPERS_PER_TASK=10
MAX_PDF_DOWNLOADS=5
ENABLE_PDF_DOWNLOAD=true
FETCH_FULL_PAGE=true

# RAG
ENABLE_RAG=true
RAG_COLLECTION_NAME=deep_research

# 笔记
ENABLE_NOTES=true
NOTES_WORKSPACE=./notes

# 流式摘要
STRIP_THINKING_TOKENS=true
USE_TOOL_CALLING=false

# Zotero（可选）
ENABLE_ZOTERO=false
# ZOTERO_LIBRARY_ID=xxxxx
# ZOTERO_API_KEY=xxxxx
# ZOTERO_LIBRARY_TYPE=user

# CAMEL 同行评议（可选）
ENABLE_CAMEL_REVIEW=false
CAMEL_MAX_REVIEW_ROUNDS=3
```

### 4. 启动 LLM 后端

任选一种本地推理后端：

```bash
# 方式 A: Ollama
ollama pull llama3.2
ollama serve

# 方式 B: LMStudio
# 启动 LMStudio 并加载模型，开启本地服务器（默认 :1234）
```

### 5. 启动后端 API

```bash
cd backend/src
python main.py                 # http://0.0.0.0:8000
# 或
uvicorn main:app --reload --port 8000
```

接口文档：http://localhost:8000/docs

### 6. 启动前端

```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173
```

## 📡 API 参考

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/healthz` | 健康检查 |
| `POST` | `/research` | 同步研究，等待完整报告返回 |
| `POST` | `/research/stream` | SSE 流式研究，实时推送进度与摘要 |

**请求体**（`ResearchRequest`）：

```json
{
  "topic": "大语言模型在科研中的应用",
  "search_api": "academic",
  "venue_tiers": ["ccf_a", "arxiv"],
  "papers_per_task": 10,
  "max_pdf_downloads": 5
}
```

**响应**（`ResearchResponse`）：

```json
{
  "report_markdown": "# 研究报告\n...",
  "todo_items": [
    {
      "id": 1,
      "title": "...",
      "intent": "...",
      "query": "...",
      "status": "completed",
      "summary": "...",
      "sources_summary": "...",
      "note_id": "...",
      "note_path": "..."
    }
  ]
}
```

**SSE 事件类型**：`plan` / `task_start` / `search` / `pdf` / `rag` / `summary_chunk` / `summary_done` / `synthesis` / `done` / `error`

## ⚙️ 配置项

所有配置项均通过环境变量加载，HTTP 请求参数会覆盖环境变量。详见 [backend/src/config.py](backend/src/config.py) 的 `Configuration` 类。

## 📄 License

MIT
