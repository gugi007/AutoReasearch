# HelloAgents Deep Researcher 改进方案

## 1. 项目现状分析

### 1.1 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Python 3.10+ |
| 前端框架 | Vue 3 + Vite + TypeScript |
| Agent 框架 | HelloAgents 0.2.9（教学级多 Agent 框架） |
| LLM | Ollama / LMStudio / OpenAI 兼容接口 |
| 搜索引擎 | DuckDuckGo / Tavily / Perplexity / SearXNG |
| 笔记系统 | NoteTool（本地 Markdown 文件） |

### 1.2 当前架构

```
用户输入研究主题
    ↓
Todo Planner（拆分为 3-5 个子任务）
    ↓
Search（DuckDuckGo / Tavily 搜索）
    ↓
Summarizer（总结每个任务的搜索结果）
    ↓
Reporter（整合所有任务生成报告）
    ↓
MD 报告输出 + NoteTool 笔记
```

### 1.3 当前 Agent 数量

| Agent | 名称 | 职责 |
|-------|------|------|
| `todo_agent` | 研究规划专家 | 拆分主题为子任务 |
| `_summarizer_factory` | 任务总结专家 | 总结每个任务的搜索结果 |
| `report_agent` | 报告撰写专家 | 整合所有任务生成报告 |

**本质是线性流水线**：Planner → Summarizer → Reporter，不是真正的 Multi-Agent 协作。

### 1.4 HelloAgents 依赖分析

项目源码中直接使用 HelloAgents 的文件：

| 文件 | 导入的组件 | 作用 |
|------|-----------|------|
| `agent.py` | `HelloAgentsLLM`, `ToolAwareSimpleAgent`, `ToolRegistry`, `NoteTool` | LLM 客户端 + Agent 创建 |
| `services/planner.py` | `ToolAwareSimpleAgent` | Planner Agent 类型标注 |
| `services/reporter.py` | `ToolAwareSimpleAgent` | Reporter Agent 类型标注 |
| `services/summarizer.py` | `ToolAwareSimpleAgent` | Summarizer Agent 类型标注 |
| `services/search.py` | `SearchTool` | 搜索工具 |

HelloAgents 提供的核心抽象只有 4 个：

```
HelloAgentsLLM          → LLM 客户端（OpenAI 兼容封装）
ToolAwareSimpleAgent    → Agent（LLM + 工具调用 + 历史管理）
SearchTool              → 搜索后端（DuckDuckGo/Tavily 混合）
NoteTool                → 笔记持久化
```

---

## 2. 改进方案

### 2.1 核心改进方向

| 序号 | 改进项 | 解决的痛点 |
|------|--------|-----------|
| 1 | 接入 Google Scholar 学术搜索 | 当前只有通用 Web 搜索，无法获取学术文献 |
| 2 | Zotero 文献管理集成 | 文献散落各处，无法系统管理 |
| 3 | RAG 文献向量库 | 长文献无法高效检索关键段落 |
| 4 | CAMEL Researcher-Reviewer 工作流 | 缺少文献阅读的质量校验机制 |
| 5 | PPT 导出 | 输出形式单一 |

### 2.2 技术选型：LangGraph + CAMEL

| 框架 | 擅长 | 用途 |
|------|------|------|
| **LangGraph** | 状态机、DAG 流程、条件路由、并行执行、checkpoint | 全局工作流编排 |
| **CAMEL** | 角色扮演、多轮对话、Agent 社会 | Reader ↔ Reviewer 迭代审查 |

**分工**：LangGraph 是调度中心，CAMEL 是阅读审查车间。

### 2.3 目标架构：9 个 Agent

```
┌─────────────────────────────────────────────────────┐
│                   Orchestrator (协调者)               │
│              LangGraph StateGraph 编排               │
└──────────┬──────────┬──────────┬──────────┬──────────┘
           │          │          │          │
     ┌─────▼──┐ ┌────▼───┐ ┌───▼────┐ ┌───▼────┐
     │ Planner│ │Searcher│ │Reader  │ │Reviewer│
     │ 规划师 │ │ 检索员 │ │ 阅读员 │ │ 审查员 │
     └────────┘ └────┬───┘ └───┬────┘ └───┬────┘
                     │         │          │
                ┌────▼───┐ ┌──▼─────┐ ┌──▼──────┐
                │Scholar │ │RAG     │ │Citation │
                │学术搜索│ │向量检索│ │引用校验 │
                └────────┘ └────────┘ └─────────┘

     ┌──────────┐  ┌──────────┐  ┌──────────┐
     │Synthesizer│ │PPT Writer│ │ Zotero   │
     │ 综合撰写 │  │ PPT生成  │ │文献管理员│
     └──────────┘  └──────────┘  └──────────┘
```

9 个 Agent 详细职责：

| # | Agent | 名称 | 输入 | 输出 |
|---|-------|------|------|------|
| 1 | **Planner** | 研究规划师 | 用户主题 | 3-5 个子任务 + 学术关键词 |
| 2 | **Searcher** | 学术检索员 | 关键词 | 高引文献列表（标题/作者/引用数/摘要） |
| 3 | **Zotero Manager** | 文献管理员 | 文献元数据 | Zotero 条目 key + 全文 |
| 4 | **RAG Indexer** | 向量索引员 | 文献全文 | 向量化的 chunk 入库 |
| 5 | **Reader** | 文献阅读员 | RAG 检索结果 + 任务意图 | 结构化阅读笔记 |
| 6 | **Reviewer** | 质量审查员 | Reader 的笔记 + 原文 | 校验报告（PASS / 修改建议） |
| 7 | **Citation Checker** | 引用校验员 | 引用列表 + 原文 | 引用准确性报告 |
| 8 | **Synthesizer** | 综合撰写员 | 所有任务笔记（已审查通过） | 最终结构化报告 |
| 9 | **PPT Writer** | 演示文稿生成员 | 最终报告 | .pptx 文件 |

### 2.4 改进后的工作流（支持异步并行）

```
Planner（顺序执行）
    │
    ▼
┌─── Send("task_pipeline", task_1) ──┐
├─── Send("task_pipeline", task_2) ──┤  LangGraph Send API 并行派发
├─── Send("task_pipeline", task_3) ──┤
└────────────────────────────────────┘
    │         │         │
    ▼         ▼         ▼
┌───────┐ ┌───────┐ ┌───────┐
│Task 1 │ │Task 2 │ │Task 3 │    三个任务同时异步执行
│       │ │       │ │       │
│Search │ │Search │ │Search │    每个任务内部串行：
│  ↓    │ │  ↓    │ │  ↓    │    Search → Zotero → RAG → CAMEL
│Zotero │ │Zotero │ │Zotero │
│  ↓    │ │  ↓    │ │  ↓    │
│RAG    │ │RAG    │ │RAG    │
│  ↓    │ │  ↓    │ │  ↓    │
│CAMEL  │ │CAMEL  │ │CAMEL  │
└───┬───┘ └───┬───┘ └───┬───┘
    │         │         │
    └─────────┼─────────┘
              │  Fan-in 汇聚（LangGraph 自动等待全部完成）
              ▼
        Synthesizer（顺序执行）
              │
              ▼
         PPT Export
              │
              ▼
            输出
```

**关键特性：**
- 任务间并行：3 个任务同时执行，总耗时 = 最慢单任务耗时
- 任务内串行：每个任务的 Search → Zotero → RAG → CAMEL 有依赖关系
- 错误隔离：单个任务失败不影响其他任务
- Fan-in 汇聚：LangGraph 自动等待所有任务完成后进入 Synthesizer

---

## 3. HelloAgents 替换方案

### 3.1 替换成本评估

**结论：成本中等偏低，约 150-200 行代码改动，涉及 5 个文件。**

| HelloAgents 组件 | LangChain 替代 | 改动量 |
|------------------|---------------|--------|
| `HelloAgentsLLM` | `ChatOpenAI` / `ChatOllama` | 改 `_init_llm` 方法，~20 行 |
| `ToolAwareSimpleAgent` | LangGraph 节点函数 | 改 3 个 Service 类，每个 ~30 行 |
| `SearchTool` | `TavilySearch` / `DuckDuckGoSearch` | 改 `search.py`，~40 行 |
| `NoteTool` | 保留原样，或封装为 LangChain Tool | 几乎不动 |
| `ToolRegistry` | `langchain_core.tools` | 改 `agent.py` 注册部分，~15 行 |

### 3.2 替换映射

```python
# 之前 (HelloAgents)
from hello_agents import HelloAgentsLLM, ToolAwareSimpleAgent

llm = HelloAgentsLLM(model="llama3.2", provider="ollama")
agent = ToolAwareSimpleAgent(name="规划师", llm=llm, system_prompt="...")
response = agent.run(prompt)

# 之后 (LangChain)
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

llm = ChatOpenAI(model="llama3.2", base_url="http://localhost:11434/v1")
response = llm.invoke([SystemMessage(content="..."), HumanMessage(content=prompt)])
```

```python
# 之前 (SearchTool)
from hello_agents.tools import SearchTool

tool = SearchTool(backend="hybrid")
result = tool.run({"input": query, "backend": "duckduckgo"})

# 之后 (LangChain)
from langchain_community.tools import DuckDuckGoSearchRun

search = DuckDuckGoSearchRun()
result = search.invoke(query)
```

### 3.3 完整改动清单

```
文件                           改动类型        工作量
─────────────────────────────────────────────────
config.py                      微调           10min
  └─ LLM provider 配置适配 LangChain 的 ChatOpenAI 参数

agent.py                       重写           1h
  └─ _init_llm → ChatOpenAI
  └─ _create_tool_aware_agent → 删除（LangGraph 节点替代）
  └─ DeepResearchAgent → 改为 LangGraph 图的编排器

services/planner.py            重写           30min
  └─ ToolAwareSimpleAgent.run → ChatOpenAI.invoke

services/summarizer.py         删除           0
  └─ 被 CAMEL Society 替代

services/reporter.py           重写           30min
  └─ 同 planner.py

services/search.py             重写           30min
  └─ SearchTool → LangChain search 或保留自定义

services/tool_events.py        不动           0
services/text_processing.py    不动           0
services/notes.py              不动           0
main.py                        微调           15min
  └─ 改为调用 LangGraph 图

pyproject.toml                 修改           5min
  └─ 移除 hello-agents，新增 langgraph/langchain/camel
```

**总工作量：约 3 小时。**

---

## 4. 具体实现步骤

### Phase 1：学术搜索 + Zotero 集成（基础能力）

**Step 1.1 — 扩展 SearchAPI**

```python
# config.py
class SearchAPI(Enum):
    # ... existing ...
    GOOGLE_SCHOLAR = "google_scholar"
    SEMANTIC_SCHOLAR = "semantic_scholar"
```

**Step 1.2 — 新建 `services/scholar_search.py`**

- 封装 Google Scholar MCP 调用
- 返回结构化结果：`title, authors, year, citations, abstract, url, doi`
- 按引用数排序，取 top-10

**Step 1.3 — 新建 `services/zotero_manager.py`**

- 封装 Zotero MCP 操作：
  - `create_collection(task_name)` → 创建任务文献集
  - `add_paper(paper_metadata)` → 导入文献
  - `get_fulltext(item_key)` → 获取全文用于 RAG
- 在任务执行中，搜索完成后自动调用导入

**Step 1.4 — 修改 `services/search.py` 的 `dispatch_search`**

- 新增 `google_scholar` 分支
- 搜索完成后自动触发 Zotero 导入

### Phase 2：RAG 文献向量库

**Step 2.1 — 新增依赖**

```toml
# pyproject.toml
"chromadb>=0.4.0",
"sentence-transformers>=2.2.0",
```

**Step 2.2 — 新建 `services/rag_engine.py`**

```python
class RAGEngine:
    def __init__(self, collection_name="deep_research"):
        self.client = chromadb.PersistentClient(path="./vector_db")
        self.collection = self.client.get_or_create_collection(collection_name)

    def ingest_paper(self, item_key: str, fulltext: str):
        """分块 + 向量化入库"""
        chunks = self._chunk_text(fulltext, chunk_size=512, overlap=64)
        for i, chunk in enumerate(chunks):
            self.collection.add(
                ids=[f"{item_key}_{i}"],
                documents=[chunk],
                metadatas=[{"item_key": item_key, "chunk_index": i}]
            )

    def query(self, question: str, top_k: int = 5) -> list[str]:
        """检索最相关段落"""
        results = self.collection.query(query_texts=[question], n_results=top_k)
        return results["documents"][0]
```

**Step 2.3 — 集成到 Researcher Agent**

- Researcher 在阅读文献前，先调用 `rag_engine.query(task.query + task.intent)`
- 检索结果作为 context 的一部分传入 prompt

### Phase 3：CAMEL Researcher-Reviewer 工作流

**Step 3.1 — CAMEL Society 嵌入到 LangGraph 节点**

```python
# graph/nodes/camel_review.py
from camel.societies import RolePlaying
from camel.messages import BaseMessage

def camel_review_node(state: ResearchState) -> dict:
    """LangGraph 节点：内部运行 CAMEL Researcher-Reviewer 对话"""

    task = state["tasks"][state["current_task_idx"]]
    rag_context = query_rag(task["query"], task["intent"])

    # 构建 CAMEL 角色
    researcher_sys = BaseMessage.make_assistant_message(
        role_name="文献研究员",
        content="...",
    )

    reviewer_sys = BaseMessage.make_assistant_message(
        role_name="质量审查员",
        content="...",
    )

    # CAMEL RolePlaying 对话
    society = RolePlaying(
        assistant_role_name="文献研究员",
        assistant_agent_kwargs={"system_message": researcher_sys},
        user_role_name="质量审查员",
        user_agent_kwargs={"system_message": reviewer_sys},
        task_prompt=f"请基于以下文献完成研究发现的提取与审查：\n\n{rag_context}",
        with_task_specify=False,
        output_language="Chinese",
    )

    # 迭代对话
    chat_history = []
    max_rounds = 3
    for round_num in range(max_rounds):
        assistant_msg, user_msg = society.step(chat_history[-1] if chat_history else None)
        chat_history.append(assistant_msg)
        chat_history.append(user_msg)

        if "VERDICT: PASS" in user_msg.content:
            break

    final_notes = chat_history[-2].content
    return {"task_notes": [{"task_id": task["id"], "notes": final_notes}]}
```

**Step 3.2 — Prompt 设计**

Researcher prompt 核心：
```
你是一名文献研究员。基于检索到的文献段落，提取：
1. 关键发现与创新点
2. 研究方法与技术路线
3. 局限性与未来方向
4. 引用信息（作者、年份、期刊）
```

Reviewer prompt 核心：
```
你是一名质量审查员。检查 Researcher 的输出：
1. 引用是否与原文一致
2. 结论是否被证据充分支持
3. 是否遗漏重要文献或关键发现
4. 逻辑是否自洽
输出 "PASS" 或具体修改建议。
```

### Phase 4：PPT 导出

**Step 4.1 — 新增依赖**

```toml
"python-pptx>=0.6.21",
```

**Step 4.2 — 新建 `services/ppt_exporter.py`**

```python
class PPTExporter:
    def export(self, report: str, tasks: list, topic: str) -> str:
        prs = Presentation()
        # 封面
        self._add_title_slide(prs, topic)
        # 背景概览
        self._add_section(prs, "背景概览", self._extract_section(report, "背景"))
        # 核心发现（按任务）
        for task in tasks:
            self._add_section(prs, task.title, task.summary)
        # 参考文献
        self._add_references(prs, tasks)
        output_path = f"reports/{topic[:30]}.pptx"
        prs.save(output_path)
        return output_path
```

### Phase 5：前端适配

**Step 5.1 — 搜索引擎选择增加 `google_scholar`**

```vue
<option value="google_scholar">Google Scholar</option>
```

**Step 5.2 — 任务详情展示增加**

- Zotero 文献列表（带链接）
- RAG 检索到的关键段落
- Reviewer 审查记录

**Step 5.3 — 导出按钮**

```vue
<button @click="exportPPT">导出 PPT</button>
<button @click="exportZoteroCollection">导出到 Zotero</button>
```

---

## 5. LangGraph 主图设计（异步并行版）

### 5.1 状态定义

```python
# graph/state.py
from typing import TypedDict, Annotated
import operator

class ResearchState(TypedDict):
    topic: str
    tasks: list[dict]                         # Planner 输出
    papers: Annotated[list, operator.add]     # 搜到的文献（累加）
    zotero_keys: Annotated[list, operator.add]  # Zotero 条目 key
    task_notes: Annotated[list, operator.add]   # CAMEL 输出的阅读笔记（累加）
    review_results: Annotated[list, operator.add]  # Reviewer 审查结果（累加）
    final_report: str
    ppt_path: str
    events: Annotated[list, operator.add]     # SSE 事件流（累加）


class SingleTaskState(TypedDict):
    """单个任务的子图状态"""
    topic: str
    task: dict
    papers: list
    zotero_keys: list
    rag_context: str
    task_notes: dict
```

### 5.2 主图结构（Send API 并行）

```python
# graph/workflow.py
from langgraph.graph import StateGraph, END
from langgraph.types import Send

def build_research_graph():
    graph = StateGraph(ResearchState)

    # 注册节点
    graph.add_node("planner", planner_node)
    graph.add_node("task_pipeline", task_pipeline_node)  # 单任务完整流水线
    graph.add_node("synthesizer", synthesizer_node)
    graph.add_node("ppt_export", ppt_export_node)

    # 入口
    graph.set_entry_point("planner")

    # Fan-out: Planner 之后，为每个任务派发独立的 task_pipeline
    graph.add_conditional_edges(
        "planner",
        fan_out_tasks,            # 返回 Send 列表
        ["task_pipeline"],        # 目标节点
    )

    # Fan-in: 所有任务完成后自动汇聚到 synthesizer
    graph.add_edge("task_pipeline", "synthesizer")
    graph.add_edge("synthesizer", "ppt_export")
    graph.add_edge("ppt_export", END)

    return graph.compile()


def fan_out_tasks(state: ResearchState) -> list[Send]:
    """为每个任务派发一个独立的流水线，实现并行执行"""
    sends = []
    for task in state["tasks"]:
        sends.append(
            Send("task_pipeline", {
                "topic": state["topic"],
                "task": task,
            })
        )
    return sends
```

### 5.3 单任务流水线节点（内部串行）

```python
# graph/nodes/task_pipeline.py

async def task_pipeline_node(state: SingleTaskState) -> dict:
    """单个任务的完整流水线：Search → Zotero → RAG → CAMEL"""
    task = state["task"]
    topic = state["topic"]

    # Step 1: 学术搜索（异步）
    papers = await asyncio.to_thread(google_scholar_search, task["query"])

    # Step 2: Zotero 导入（异步）
    zotero_keys = []
    for paper in papers:
        key = await asyncio.to_thread(zotero_add_item, paper)
        zotero_keys.append(key)

    # Step 3: RAG 索引（异步）
    fulltexts = []
    for key in zotero_keys:
        text = await asyncio.to_thread(zotero_get_fulltext, key)
        fulltexts.append(text)
    await asyncio.to_thread(rag_index, zotero_keys, fulltexts)

    # Step 4: CAMEL 审查（异步）
    rag_context = await asyncio.to_thread(query_rag, task["query"], task["intent"])
    notes = await run_camel_review(task, rag_context)

    return {
        "papers": papers,
        "zotero_keys": zotero_keys,
        "task_notes": [notes],
    }
```

### 5.4 异步 CAMEL 审查

```python
# graph/nodes/camel_review.py

async def run_camel_review(task: dict, rag_context: str) -> dict:
    """异步运行 CAMEL Researcher-Reviewer 对话"""
    researcher_sys = BaseMessage.make_assistant_message(
        role_name="文献研究员",
        content="...",
    )
    reviewer_sys = BaseMessage.make_assistant_message(
        role_name="质量审查员",
        content="...",
    )

    society = RolePlaying(
        assistant_role_name="文献研究员",
        assistant_agent_kwargs={"system_message": researcher_sys},
        user_role_name="质量审查员",
        user_agent_kwargs={"system_message": reviewer_sys},
        task_prompt=f"请基于以下文献完成研究发现的提取与审查：\n\n{rag_context}",
        with_task_specify=False,
        output_language="Chinese",
    )

    chat_history = []
    max_rounds = 3
    for round_num in range(max_rounds):
        assistant_msg, user_msg = await asyncio.to_thread(
            society.step, chat_history[-1] if chat_history else None
        )
        chat_history.append(assistant_msg)
        chat_history.append(user_msg)
        if "VERDICT: PASS" in user_msg.content:
            break

    return {
        "task_id": task["id"],
        "notes": chat_history[-2].content,
        "rounds": len(chat_history) // 2,
    }
```

### 5.5 调用方式（异步流式）

```python
# main.py
graph = build_research_graph()

@app.post("/research/stream")
async def stream_research(payload: ResearchRequest):
    async def event_iterator():
        async for event in graph.astream(
            initial_state,
            stream_mode="updates",
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_iterator(), media_type="text/event-stream")
```

### 5.6 并行执行的性能对比

| 模式 | 3 个任务，每任务 4 步 | 预估耗时 |
|------|---------------------|----------|
| **串行（当前方案）** | 3 × 4 = 12 步顺序执行 | ~12 min |
| **任务间并行（Send API）** | 3 个任务同时跑，每任务内部串行 | ~4 min |
| **全并行（任务间 + Agent 间）** | 3 个任务 × Scholar/Web 同时跑 | ~3 min |

实际瓶颈在 **CAMEL 对话**（LLM 调用）和 **Zotero 导入**（网络 I/O），异步化收益最大。

### 5.7 错误隔离

单个任务失败不影响其他任务，通过 try-except 在 task_pipeline_node 内部处理：

```python
async def task_pipeline_node(state: SingleTaskState) -> dict:
    task = state["task"]
    try:
        # ... 正常执行
        return {"task_notes": [notes]}
    except Exception as e:
        return {
            "task_notes": [{"task_id": task["id"], "error": str(e)}],
            "events": [{"type": "task_error", "task_id": task["id"], "detail": str(e)}],
        }
```

### 5.8 更激进的并行：任务内部 Agent 并行

如果想在同一个任务内部也并行（Scholar + Web 同时搜索），可以用 Send 拆分：

```python
def build_research_graph():
    graph = StateGraph(ResearchState)

    graph.add_node("planner", planner_node)
    graph.add_node("scholar_search", scholar_search_node)
    graph.add_node("web_search", web_search_node)
    graph.add_node("zotero_import", zotero_import_node)
    graph.add_node("rag_index", rag_index_node)
    graph.add_node("camel_review", camel_review_node)
    graph.add_node("synthesizer", synthesizer_node)

    graph.set_entry_point("planner")

    # Fan-out: 同时派发 Scholar + Web 搜索
    graph.add_conditional_edges(
        "planner",
        lambda state: [
            Send("scholar_search", {"task": t}) for t in state["tasks"]
        ] + [
            Send("web_search", {"task": t}) for t in state["tasks"]
        ],
        ["scholar_search", "web_search"],
    )

    # 两个搜索都完成后汇入 zotero_import
    graph.add_edge("scholar_search", "zotero_import")
    graph.add_edge("web_search", "zotero_import")

    graph.add_edge("zotero_import", "rag_index")
    graph.add_edge("rag_index", "camel_review")
    graph.add_edge("camel_review", "synthesizer")
    graph.add_edge("synthesizer", END)

    return graph.compile()
```

---

## 6. 异步并行执行设计

### 6.1 两种并行层级

```
层级 1：任务间并行（Task-Level Parallelism）— 推荐
  任务 1 ──→ Search → Zotero → RAG → CAMEL ──┐
  任务 2 ──→ Search → Zotero → RAG → CAMEL ──┼──→ Synthesizer
  任务 3 ──→ Search → Zotero → RAG → CAMEL ──┘

层级 2：Agent 间并行（Agent-Level Parallelism）— 可选
  同一任务内：
  Search ──┬──→ Zotero ──→ RAG ──→ CAMEL
           └──→ Web Search（并行补充）
```

### 6.2 并行机制：LangGraph Send API

```python
from langgraph.types import Send

def fan_out_tasks(state: ResearchState) -> list[Send]:
    """为每个任务派发独立的流水线"""
    return [
        Send("task_pipeline", {"topic": state["topic"], "task": task})
        for task in state["tasks"]
    ]
```

- **Fan-out**：Planner 完成后，`Send` 为每个任务创建独立的执行上下文
- **Fan-in**：LangGraph 自动等待所有 `Send` 完成后才进入下一个节点
- **结果合并**：通过 `Annotated[list, operator.add]` 自动累加多个任务的结果

### 6.3 异步节点实现

所有耗时操作使用 `asyncio.to_thread` 包装，避免阻塞事件循环：

```python
async def task_pipeline_node(state: SingleTaskState) -> dict:
    # 异步执行同步函数
    papers = await asyncio.to_thread(google_scholar_search, task["query"])
    zotero_keys = [await asyncio.to_thread(zotero_add_item, p) for p in papers]
    # ...
```

### 6.4 SSE 事件流

异步模式下，每个任务完成后立即推送事件到前端：

```python
@app.post("/research/stream")
async def stream_research(payload: ResearchRequest):
    async def event_iterator():
        async for event in graph.astream(initial_state, stream_mode="updates"):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    return StreamingResponse(event_iterator(), media_type="text/event-stream")
```

### 6.5 错误隔离

单个任务失败不影响其他任务：

```python
async def task_pipeline_node(state: SingleTaskState) -> dict:
    try:
        # ... 正常执行
        return {"task_notes": [notes]}
    except Exception as e:
        return {
            "task_notes": [{"task_id": task["id"], "error": str(e)}],
            "events": [{"type": "task_error", "task_id": task["id"]}],
        }
```

### 6.6 性能对比

| 模式 | 3 个任务，每任务 4 步 | 预估耗时 |
|------|---------------------|----------|
| **串行（当前方案）** | 3 × 4 = 12 步顺序执行 | ~12 min |
| **任务间并行（Send API）** | 3 个任务同时跑，每任务内部串行 | ~4 min |
| **全并行（任务间 + Agent 间）** | 3 个任务 × Scholar/Web 同时跑 | ~3 min |

实际瓶颈在 **CAMEL 对话**（LLM 调用）和 **Zotero 导入**（网络 I/O），异步化收益最大。

---

## 7. 新增依赖汇总

```toml
# pyproject.toml
dependencies = [
    # 移除
    # "hello-agents==0.2.9",

    # 保留
    "fastapi>=0.115.0",
    "python-dotenv==1.0.1",
    "requests>=2.31.0",
    "uvicorn[standard]>=0.32.0",
    "loguru>=0.7.3",

    # 新增 - LangGraph + LangChain
    "langgraph>=0.2.0",
    "langchain-core>=0.3.0",
    "langchain-openai>=0.2.0",
    "langchain-community>=0.3.0",

    # 新增 - CAMEL
    "camel-ai>=0.2.0",

    # 新增 - RAG
    "chromadb>=0.4.0",
    "sentence-transformers>=2.2.0",

    # 新增 - PPT 导出
    "python-pptx>=0.6.21",

    # 新增 - 学术搜索（可选）
    "scholarly>=1.7.0",

    # 新增 - 异步支持
    "aiohttp>=3.9.0",
    "aiosqlite>=0.19.0",
]
```

---

## 8. 实施优先级

| 优先级 | 模块 | 工作量 | 价值 |
|--------|------|--------|------|
| P0 | HelloAgents → LangChain 替换 | 3h | 技术栈统一 |
| P0 | Google Scholar 学术搜索 | 1-2d | 核心痛点 |
| P0 | Zotero 自动导入 | 1d | 文献管理闭环 |
| P1 | CAMEL Researcher-Reviewer | 2-3d | 报告质量核心 |
| P2 | RAG 向量库 | 2-3d | 长文献处理效率 |
| P3 | PPT 导出 | 1d | 锦上添花 |

---

## 9. 总结

| 维度 | 现状 | 改进后 |
|------|------|--------|
| Agent 数量 | 3 个（线性流水线） | 9 个（DAG + CAMEL 迭代） |
| 执行模式 | 串行（Thread 模拟） | 异步并行（LangGraph Send API + asyncio） |
| 并行粒度 | 无 | 任务间并行 + Agent 间并行 |
| 搜索来源 | 通用 Web | Google Scholar + Web |
| 文献管理 | 无 | Zotero 自动导入 |
| 文献检索 | 无 | RAG 向量库 |
| 质量校验 | 无 | Researcher ↔ Reviewer 迭代 |
| 输出格式 | MD | MD + PPT + Zotero |
| 底层框架 | HelloAgents | LangGraph + CAMEL |
| 错误处理 | 整体失败 | 单任务隔离，失败不影响其他任务 |
