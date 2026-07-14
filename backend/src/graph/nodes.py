"""Node functions for the LangGraph research workflow."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from langgraph.types import Send
from openai import OpenAI

from config import Configuration
from models import SummaryState, TodoItem
from services.note_tool import NoteTool
from services.planner import PlanningService
from services.reporter import ReportingService
from services.search import dispatch_search, prepare_research_context
from services.summarizer import SummarizationService
from services.zotero_manager import ZoteroManager

from graph.state import ResearchState, TaskPipelineInput

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Service factory
# ---------------------------------------------------------------------------


def _init_llm(config: Configuration) -> tuple[OpenAI, str]:
    """Instantiate OpenAI client and resolve model identifier."""
    provider = (config.llm_provider or "").strip()
    model_id = config.resolved_model() or "llama3.2"

    if provider == "ollama":
        base_url = config.sanitized_ollama_url()
        api_key = config.llm_api_key or "ollama"
    elif provider == "lmstudio":
        base_url = config.lmstudio_base_url
        api_key = config.llm_api_key or "lmstudio"
    else:
        base_url = config.llm_base_url or "http://localhost:11434/v1"
        api_key = config.llm_api_key or "ollama"

    client = OpenAI(base_url=base_url, api_key=api_key)
    return client, model_id


class _Services:
    """Lazy container for service instances derived from Configuration."""

    def __init__(self, config: Configuration) -> None:
        client, model = _init_llm(config)
        self.config = config
        self.planner = PlanningService(client, model, config)
        self.summarizer = SummarizationService(client, model, config)
        self.reporter = ReportingService(client, model, config)
        self.note_tool = (
            NoteTool(workspace=config.notes_workspace) if config.enable_notes else None
        )
        self.zotero: ZoteroManager | None = None
        if config.enable_zotero:
            self.zotero = ZoteroManager(
                library_id=config.zotero_library_id,
                library_type=config.zotero_library_type,
                api_key=config.zotero_api_key,
            )


# ---------------------------------------------------------------------------
# Helper: serialize task for SSE
# ---------------------------------------------------------------------------


def _serialize_task(task: TodoItem) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "intent": task.intent,
        "query": task.query,
        "status": task.status,
        "summary": task.summary,
        "sources_summary": task.sources_summary,
        "note_id": task.note_id,
        "note_path": task.note_path,
        "stream_token": task.stream_token,
    }


def _stamp_events(
    events: list[dict[str, Any]],
    run_id: str | None,
) -> list[dict[str, Any]]:
    """Attach run metadata to SSE events before they leave a graph node."""
    if not run_id:
        return events

    stamped = []
    for event in events:
        payload = dict(event)
        payload.setdefault("run_id", run_id)
        stamped.append(payload)
    return stamped


def _task_status_event(task: TodoItem, status: str, **extra: Any) -> dict[str, Any]:
    """Build the common task status event payload."""
    payload: dict[str, Any] = {
        "type": "task_status",
        "task_id": task.id,
        "status": status,
        "title": task.title,
        "intent": task.intent,
        "note_id": task.note_id,
        "note_path": task.note_path,
    }
    payload.update(extra)
    return payload


def _download_and_parse_pdfs(
    papers: list[dict[str, Any]],
    task_id: int,
    config: Configuration,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], int]:
    """Download a bounded set of PDFs and extract text for downstream context."""
    from services.pdf_downloader import PDFDownloader
    from services.pdf_parser import PDFParser

    downloader = PDFDownloader(pdf_dir=config.pdf_dir)
    parser = PDFParser()

    downloaded_papers = downloader.download_batch(
        papers,
        task_id,
        config.max_pdf_downloads,
    )

    pdf_texts: list[dict[str, str]] = []
    for paper in downloaded_papers:
        if paper.get("downloaded") and paper.get("pdf_path"):
            pdf_text = parser.extract_text(paper["pdf_path"])
            if pdf_text:
                paper["full_text"] = pdf_text
                pdf_texts.append(
                    {
                        "title": paper.get("title", ""),
                        "text": pdf_text,
                        "source": paper.get("source", ""),
                    }
                )

    download_count = sum(1 for paper in downloaded_papers if paper.get("downloaded"))
    merged_papers = downloaded_papers + papers[config.max_pdf_downloads:]
    return merged_papers, pdf_texts, download_count


def _augment_context_with_rag(
    search_result: dict[str, Any],
    pdf_texts: list[dict[str, str]],
    task: TodoItem,
    run_id: str | None,
    config: Configuration,
) -> str:
    """Index task evidence and return run/task-scoped RAG context."""
    from services.rag_engine import RAGEngine

    rag = RAGEngine(config.rag_collection_name)
    rag.ingest_search_results(task.id, search_result, run_id)

    for pdf in pdf_texts:
        if not pdf.get("text"):
            continue

        rag.ingest_search_results(
            task.id,
            {
                "results": [
                    {
                        "title": pdf.get("title", ""),
                        "content": pdf["text"],
                        "url": "",
                    }
                ]
            },
            run_id,
        )

    return rag.query(task.query, top_k=5, task_id=task.id, run_id=run_id)


# ---------------------------------------------------------------------------
# Helper: Zotero import (best-effort)
# ---------------------------------------------------------------------------


def _import_papers(
    zotero: ZoteroManager | None,
    search_result: dict[str, Any],
    task: TodoItem,
) -> None:
    """Import search results to Zotero, silently swallowing errors."""
    if not zotero or not zotero.available or not search_result:
        return

    try:
        from services.mcp.sync_wrapper import get_mcp_wrapper

        wrapper = get_mcp_wrapper()
    except Exception:
        wrapper = None

    results = search_result.get("results", [])
    if not results:
        return

    imported = 0
    for paper in results:
        try:
            if wrapper and wrapper.has_tool("zotero_add_paper"):
                authors_raw = paper.get("authors", "")
                if isinstance(authors_raw, str):
                    authors = [a.strip() for a in authors_raw.split(",") if a.strip()]
                else:
                    authors = authors_raw if isinstance(authors_raw, list) else []
                result = wrapper.call_tool(
                    "zotero_add_paper",
                    {
                        "title": paper.get("title", ""),
                        "authors": authors,
                        "year": str(paper.get("year", "")),
                        "abstract": paper.get("content", ""),
                        "url": paper.get("url", ""),
                        "doi": paper.get("doi", ""),
                        "venue": paper.get("venue", ""),
                    },
                )
                if isinstance(result, dict) and result.get("success"):
                    imported += 1
            else:
                key = zotero.add_paper_from_search_result(paper)
                if key:
                    imported += 1
        except Exception as exc:
            logger.debug("Zotero import failed for '%s': %s", paper.get("title"), exc)

    if imported:
        logger.info("Imported %d papers to Zotero for task %d", imported, task.id)


# ---------------------------------------------------------------------------
# Helper: persist final report to NoteTool
# ---------------------------------------------------------------------------


def _persist_report(
    note_tool: NoteTool | None,
    topic: str,
    report: str,
    run_id: str | None = None,
) -> dict[str, Any] | None:
    if not note_tool or not report or not report.strip():
        return None

    note_title = f"研究报告：{topic}".strip() or "研究报告"
    tags = ["deep_research", "report"]
    if run_id:
        tags.append(f"run:{run_id}")
    content = report.strip()

    response = note_tool.run(
        {
            "action": "create",
            "title": note_title,
            "note_type": "conclusion",
            "tags": tags,
            "content": content,
        }
    )

    import re

    match = re.search(r"ID:\s*([^\n]+)", response)
    note_id = match.group(1).strip() if match else None
    if not note_id:
        return None

    note_path = Path(note_tool.workspace) / f"{note_id}.md"
    return {
        "type": "report_note",
        "run_id": run_id,
        "note_id": note_id,
        "title": note_title,
        "content": content,
        "note_path": str(note_path),
    }


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def planner_node(
    state: ResearchState,
    *,
    app_config: Configuration,
) -> dict[str, Any]:
    """Plan TODO items from the research topic."""
    services = _Services(app_config)
    temp_state = SummaryState(research_topic=state["research_topic"])

    todo_items = await asyncio.to_thread(services.planner.plan_todo_list, temp_state)
    if not todo_items:
        logger.info("No TODO items generated; falling back to single task")
        todo_items = [services.planner.create_fallback_task(temp_state)]

    for index, task in enumerate(todo_items, start=1):
        task.stream_token = f"task_{task.id}"

    return {
        "todo_items": todo_items,
        "research_loop_count": 0,
        "stream_events": [
            {
                "type": "todo_list",
                "run_id": state.get("run_id"),
                "tasks": [_serialize_task(t) for t in todo_items],
                "step": 0,
            }
        ],
    }


def fan_out_tasks(state: ResearchState) -> list[Send]:
    """Conditional edge: create a Send for each TODO item."""
    return [
        Send(
            "task_pipeline",
            {
                "research_topic": state["research_topic"],
                "run_id": state["run_id"],
                "task": task,
                "todo_items": state["todo_items"],
            },
        )
        for task in state["todo_items"]
    ]


async def task_pipeline_node(
    state: TaskPipelineInput,
    *,
    app_config: Configuration,
) -> dict[str, Any]:
    """Execute search + summarize for a single task (runs in parallel)."""
    services = _Services(app_config)
    task: TodoItem = state["task"]
    run_id = state.get("run_id")
    events: list[dict[str, Any]] = []

    try:
        # -- in_progress --
        task.status = "in_progress"
        events.append(_task_status_event(task, "in_progress"))

        # -- search --
        search_result, notices, answer_text, backend = await asyncio.to_thread(
            dispatch_search, task.query, app_config, 0
        )
        task.notices = notices

        for notice in notices:
            if notice:
                events.append(
                    {
                        "type": "status",
                        "message": notice,
                        "task_id": task.id,
                    }
                )

        if not search_result or not search_result.get("results"):
            task.status = "skipped"
            events.append(_task_status_event(task, "skipped"))
            return {
                "completed_tasks": [task],
                "stream_events": _stamp_events(events, run_id),
            }

        # -- PDF download (if enabled) --
        pdf_texts = []
        download_count = 0
        logger.info("Task %d: enable_pdf_download=%s, max_pdf_downloads=%s, pdf_dir=%s",
                    task.id, app_config.enable_pdf_download, app_config.max_pdf_downloads, app_config.pdf_dir)
        if app_config.enable_pdf_download and app_config.max_pdf_downloads > 0:
            events.append(
                {
                    "type": "status",
                    "message": f"正在下载论文 PDF（最多 {app_config.max_pdf_downloads} 篇）...",
                    "task_id": task.id,
                }
            )

            papers = search_result.get("results", [])
            merged_papers, pdf_texts, download_count = await asyncio.to_thread(
                _download_and_parse_pdfs,
                papers,
                task.id,
                app_config,
            )

            # Keep all search results. The downloader only touches the first N papers.
            search_result["results"] = merged_papers
            if download_count > 0:
                events.append(
                    {
                        "type": "status",
                        "message": f"成功下载 {download_count} 篇论文 PDF",
                        "task_id": task.id,
                    }
                )
            else:
                # PDF is useful but not mandatory; continue with metadata/abstract context.
                events.append(
                    {
                        "type": "warning",
                        "message": f"任务 {task.id}「{task.title}」未下载到论文 PDF，已改用检索摘要继续分析",
                        "task_id": task.id,
                    }
                )

        # -- prepare context --
        sources_summary, context = await asyncio.to_thread(
            prepare_research_context, search_result, answer_text, app_config
        )
        task.sources_summary = sources_summary

        # 将 PDF 全文添加到上下文
        if pdf_texts:
            pdf_context_parts = ["\n\n--- 论文全文 ---"]
            for pdf in pdf_texts:
                pdf_context_parts.append(f"\n## {pdf['title']}\n{pdf['text'][:10000]}")
            context = context + "\n".join(pdf_context_parts)

        events.append(
            {
                "type": "sources",
                "task_id": task.id,
                "latest_sources": sources_summary,
                "raw_context": context,
                "backend": backend,
                "note_id": task.note_id,
                "note_path": task.note_path,
            }
        )

        # -- zotero import (best-effort) --
        await asyncio.to_thread(_import_papers, services.zotero, search_result, task)

        # -- RAG index & retrieve --
        if app_config.enable_rag:
            rag_context = await asyncio.to_thread(
                _augment_context_with_rag,
                search_result,
                pdf_texts,
                task,
                run_id,
                app_config,
            )
            if rag_context:
                context = context + "\n\n--- RAG 补充资料 ---\n" + rag_context

        # -- summarize --
        temp_state = SummaryState(research_topic=state["research_topic"])
        temp_state.todo_items = state["todo_items"]

        summary_text = await asyncio.to_thread(
            services.summarizer.summarize_task, temp_state, task, context
        )

        # -- CAMEL review (optional) --
        if app_config.enable_camel_review:
            from services.camel_review import CAMELReviewer

            reviewer = CAMELReviewer(app_config)
            reviewed = await asyncio.to_thread(
                reviewer.review,
                task,
                context,
                summary_text,
                app_config.camel_max_review_rounds,
            )
            if reviewed:
                summary_text = reviewed

        task.summary = summary_text.strip() if summary_text else "暂无可用信息"
        task.status = "completed"

        events.append(
            _task_status_event(
                task,
                "completed",
                summary=task.summary,
                sources_summary=task.sources_summary,
            )
        )

        return {
            "completed_tasks": [task],
            "web_research_results": [context],
            "sources_gathered": [sources_summary],
            "research_loop_count": 1,
            "stream_events": _stamp_events(events, run_id),
        }

    except Exception as exc:
        logger.exception("Task %d execution failed", task.id, exc_info=exc)
        task.status = "failed"
        events.append(
            _task_status_event(task, "failed", detail=str(exc))
        )
        return {
            "completed_tasks": [task],
            "stream_events": _stamp_events(events, run_id),
        }


async def synthesizer_node(
    state: ResearchState,
    *,
    app_config: Configuration,
) -> dict[str, Any]:
    """Generate the final report and persist it."""
    services = _Services(app_config)
    run_id = state.get("run_id")
    events: list[dict[str, Any]] = []

    # Reconstruct SummaryState for the reporter
    temp_state = SummaryState(research_topic=state["research_topic"])
    task_results = state.get("completed_tasks") or state.get("todo_items", [])
    temp_state.todo_items = sorted(task_results, key=lambda item: item.id)
    temp_state.web_research_results = state.get("web_research_results", [])
    temp_state.sources_gathered = state.get("sources_gathered", [])
    temp_state.research_loop_count = state.get("research_loop_count", 0)

    report = await asyncio.to_thread(services.reporter.generate_report, temp_state)

    # Persist report note
    note_event = await asyncio.to_thread(
        _persist_report, services.note_tool, state["research_topic"], report, run_id
    )
    note_id = None
    note_path = None
    if note_event:
        events.append(note_event)
        note_id = note_event.get("note_id")
        note_path = note_event.get("note_path")

    events.append(
        {
            "type": "final_report",
            "run_id": run_id,
            "report": report,
            "note_id": note_id,
            "note_path": note_path,
        }
    )
    events.append({"type": "done", "run_id": run_id})

    return {
        "structured_report": report,
        "running_summary": report,
        "report_note_id": note_id,
        "report_note_path": note_path,
        "stream_events": _stamp_events(events, run_id),
    }
