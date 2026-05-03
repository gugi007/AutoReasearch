# AutoResearch 项目文档

## 项目目标
针对现有深度研究工具缺乏学术文献检索与质量校验的问题，基于 LangGraph + CAMEL 构建 9-Agent 协作的全链路学术研究系统，支持从文献搜索、自动导入、向量检索到多轮审查的端到端研究流程。

## 当前架构 vs 目标架构

**现状**：3-Agent 线性流水线（Planner → Summarizer → Reporter），通过 OpenAI client 直接调用 LLM，Thread 并发执行任务。

**目标**：9-Agent DAG 编排，LangGraph 状态图驱动，CAMEL 负责文献阅读审查，支持任务间异步并行。

| 维度 | 现状 | 目标 |
|---|---|---|
| Agent 数量 | 3 个（线性） | 9 个（DAG + CAMEL 迭代） |
| 编排框架 | Thread + Queue | LangGraph StateGraph |
| 执行模式 | 串行（Thread 模拟并行） | 异步并行（Send API + asyncio） |
| 搜索来源 | DuckDuckGo + Google Scholar | 同左（已实现） |
| 文献管理 | Zotero（pyzotero + MCP） | 同左（已实现） |
| 文献检索 | 无 | RAG 向量库（ChromaDB） |
| 质量校验 | 无 | CAMEL Researcher ↔ Reviewer 迭代 |
| 输出格式 | MD 报告 | MD + PPT + Zotero |

## 技术栈

| 层 | 现状 | 目标新增 |
|---|---|---|
| 前端 | Vue 3 + Vite + TypeScript | — |
| 后端框架 | FastAPI (Python) | — |
| LLM 调用 | OpenAI client（兼容 Ollama/LMStudio） | LangChain ChatOpenAI |
| 编排引擎 | Thread + Queue | LangGraph StateGraph |
| Agent 对话 | 无 | CAMEL RolePlaying |
| 文献管理 | Zotero（pyzotero + MCP） | — |
| 学术搜索 | scholarly（Google Scholar） | — |
| 向量检索 | 无 | ChromaDB + sentence-transformers |
| 笔记系统 | NoteTool（本地 Markdown） | — |

## 9-Agent 目标架构

```
Orchestrator (LangGraph StateGraph)
    │
Planner → [任务并行派发] → task_pipeline × N
                               │
                         Search → Zotero → RAG → CAMEL(Reader ↔ Reviewer)
                               │
                         Synthesizer → PPT Export
```

| # | Agent | 职责 | 对应文件 | 状态 |
|---|---|---|---|---|
| 1 | Planner | 研究规划，分解子任务 | planner.py | 已实现 |
| 2 | Searcher | 学术/通用检索 | search.py + scholar_search.py | 已实现 |
| 3 | Zotero Manager | 文献导入管理 | zotero_manager.py | 已实现 |
| 4 | RAG Indexer | 向量索引与检索 | （待建） | 未开始 |
| 5 | Reader | 文献阅读员 | （待建） | 未开始 |
| 6 | Reviewer | 质量审查员 | （待建） | 未开始 |
| 7 | Citation Checker | 引用校验 | （待建） | 未开始 |
| 8 | Synthesizer | 综合撰写 | reporter.py（需重写） | 待改造 |
| 9 | PPT Writer | PPT 导出 | （待建） | 未开始 |

## 目录结构

```
AutoReasearch/
├── backend/
│   └── src/
│       ├── agent.py            # 当前：Thread 编排器；目标：LangGraph 图编排
│       ├── main.py             # FastAPI 入口
│       ├── config.py           # 配置管理（含 SearchAPI 枚举、Zotero 配置）
│       ├── models.py           # 数据模型（SummaryState, TodoItem）
│       ├── prompts.py          # Agent 提示词模板
│       ├── utils.py            # 工具函数
│       └── services/
│           ├── planner.py          # 规划服务
│           ├── search.py           # 通用搜索（DuckDuckGo）
│           ├── scholar_search.py   # 学术搜索（Google Scholar）
│           ├── summarizer.py       # 摘要服务
│           ├── reporter.py         # 报告生成
│           ├── notes.py            # 笔记管理
│           ├── note_tool.py        # NoteTool 工具
│           ├── search_tool.py      # 搜索工具封装
│           ├── text_processing.py  # 文本处理
│           ├── tool_events.py      # 工具事件追踪
│           ├── zotero_manager.py   # Zotero 管理器（pyzotero）
│           └── mcp/
│               ├── client.py           # MCP 客户端
│               ├── scholar_server.py   # Scholar MCP 服务端
│               ├── sync_wrapper.py     # 同步包装器
│               └── zotero_server.py    # Zotero MCP 服务端
├── frontend/                   # Vue 3 前端
├── IMPROVEMENT_PLAN.md         # 详细改进方案（Phase 1-5）
└── CLAUDE.md                   # 本文件
```

## 关键约定

- LLM 通过 OpenAI client 调用，兼容 Ollama / LMStudio / 自定义端点
- Agent 提示词集中在 `prompts.py` 管理
- MCP 用于连接外部工具（Zotero、Scholar Search）
- 前后端通过 API 通信，后端入口在 `main.py`
- 状态模型定义在 `models.py`（SummaryState + TodoItem）
- 任务并行通过 Thread + Queue 实现（目标改为 LangGraph Send API）

## 实施路线（参考 IMPROVEMENT_PLAN.md）

| Phase | 内容 | 状态 |
|---|---|---|
| Phase 1 | 学术搜索 + Zotero 集成 | 已完成 |
| Phase 2 | RAG 文献向量库（ChromaDB） | 未开始 |
| Phase 3 | CAMEL Researcher-Reviewer 工作流 | 未开始 |
| Phase 4 | PPT 导出 | 未开始 |
| Phase 5 | 前端适配 | 未开始 |
| Phase 0 | HelloAgents → LangChain 替换 | 已完成（直接用 OpenAI client） |

## 编码规范

- Python 代码遵循项目已有的函数式风格
- 前端使用 Vue 3 组合式 API（Composition API）
- 新增 Agent 需同步更新 `agent.py` 中的编排逻辑和 `prompts.py` 中的提示词
