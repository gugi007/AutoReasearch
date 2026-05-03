# 进度记录

## 当前状态
Phase 1（学术搜索 + Zotero）已完成，项目准备进入 Phase 2（RAG 向量库）。

## 已完成

| 事项 | 说明 |
|---|---|
| HelloAgents 替换 | 已移除 HelloAgents 依赖，改用 OpenAI client 直接调用 LLM |
| 3-Agent 线性流水线 | Planner → Summarizer → Reporter 工作流可运行 |
| Google Scholar 学术搜索 | scholar_search.py 基于 scholarly 库实现，支持年份过滤、引用数排序 |
| Zotero 文献管理 | zotero_manager.py 基于 pyzotero 实现，支持创建集合、导入文献、获取全文 |
| MCP 服务端 | scholar_server.py 和 zotero_server.py 已实现 |
| MCP 客户端 | client.py + sync_wrapper.py 已实现，agent.py 中已集成 Zotero 自动导入 |
| 配置扩展 | config.py 新增 SearchAPI.GOOGLE_SCHOLAR、Zotero 相关配置项 |
| 改进计划 | IMPROVEMENT_PLAN.md 已编写，包含完整的 5-Phase 实施方案 |

## 待完成

| 事项 | 优先级 | 说明 |
|---|---|---|
| RAG 向量库（Phase 2） | P2 | 新建 rag_engine.py，ChromaDB + sentence-transformers |
| CAMEL 审查工作流（Phase 3） | P1 | Researcher ↔ Reviewer 迭代对话，嵌入 LangGraph 节点 |
| LangGraph 状态图编排 | P0 | 替换 Thread + Queue，实现 Send API 任务间并行 |
| PPT 导出（Phase 4） | P3 | python-pptx，报告转 PPT |
| 前端适配（Phase 5） | P2 | Scholar 搜索选项、Zotero 文献列表、PPT 导出按钮 |
| 新增依赖安装 | P0 | langgraph, langchain-core, langchain-openai, camel-ai, chromadb, sentence-transformers, python-pptx |

## 关键决策
- HelloAgents 直接替换为 OpenAI client，未引入 LangChain（降低了迁移成本）
- Zotero 导入支持两种方式：MCP 调用（优先）和 pyzotero 直接调用（回退）
- 任务并行当前用 Thread 模拟，目标改为 LangGraph Send API 实现真正的异步并行
