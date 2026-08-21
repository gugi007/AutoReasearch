"""FastAPI entrypoint exposing the DeepResearchAgent via HTTP."""

#main.py 是整个项目的 HTTP 入口 ：用 FastAPI 注册了 3 个 API 端点（1 个健康检查 + 2 个研究接口）
# 配合 lifespan 管理生命周期、日志记录、密钥脱敏等辅助功能，实现前后端的数据交互。
from __future__ import annotations

import json
import sys
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from config import Configuration, SearchAPI
from agent import DeepResearchAgent

# 添加控制台日志处理程序
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <4}</level> | <cyan>using_function:{function}</cyan> | <cyan>{file}:{line}</cyan> | <level>{message}</level>",
    colorize=True,
)


# 添加错误日志文件处理程序
logger.add(
    sink=sys.stderr,
    level="ERROR",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <4}</level> | <cyan>using_function:{function}</cyan> | <cyan>{file}:{line}</cyan> | <level>{message}</level>",
    colorize=True,
)


class ResearchRequest(BaseModel):
    """Payload for triggering a research run."""

    topic: str = Field(..., description="Research topic supplied by the user")
    search_api: SearchAPI | None = Field(
        default=None,
        description="Override the default search backend configured via env",
    )
    venue_tiers: list[str] | None = Field(
        default=None,
        description="文献分区筛选（可多选）：ccf_a, ccf_b, ccf_c, jcr_q1~q4, arxiv",
    )
    papers_per_task: int | None = Field(
        default=None,
        description="每子任务搜索文献篇数",
    )
    max_pdf_downloads: int | None = Field(
        default=None,
        description="每子任务最大 PDF 下载数量",
    )


class ResearchResponse(BaseModel):
    """HTTP response containing the generated report and structured tasks."""

    report_markdown: str = Field(
        ..., description="Markdown-formatted research report including sections"
    )
    todo_items: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Structured TODO items with summaries and sources",
    )


def _mask_secret(value: Optional[str], visible: int = 4) -> str:
    """Mask sensitive tokens while keeping leading and trailing characters."""
    if not value:
        return "unset"

    if len(value) <= visible * 2:
        return "*" * len(value)

    return f"{value[:visible]}...{value[-visible:]}"


def _build_config(payload: ResearchRequest) -> Configuration:
    overrides: Dict[str, Any] = {}

    if payload.search_api is not None:
        overrides["search_api"] = payload.search_api

    if payload.venue_tiers:
        overrides["venue_tiers"] = payload.venue_tiers

    if payload.papers_per_task is not None:
        overrides["papers_per_task"] = payload.papers_per_task

    if payload.max_pdf_downloads is not None:
        overrides["max_pdf_downloads"] = payload.max_pdf_downloads

    return Configuration.from_env(overrides=overrides)

# FastAPI 生命周期管理器，用于在应用启动和关闭时执行操作
# @asynccontextmanager 装饰器：将普通函数变为异步上下文管理器
@asynccontextmanager 
async def lifespan(app: FastAPI):
    # 启动时执行
    config = Configuration.from_env()

    if config.llm_provider == "ollama":
        base_url = config.sanitized_ollama_url()
    elif config.llm_provider == "lmstudio":
        base_url = config.lmstudio_base_url
    else:
        base_url = config.llm_base_url or "unset"

    logger.info(
        "DeepResearch configuration loaded: provider=%s model=%s base_url=%s search_api=%s "
        "max_loops=%s fetch_full_page=%s tool_calling=%s strip_thinking=%s api_key=%s",
        config.llm_provider,
        config.resolved_model() or "unset",
        base_url,
        (config.search_api.value if isinstance(config.search_api, SearchAPI) else config.search_api),
        config.max_web_research_loops,
        config.fetch_full_page,
        config.use_tool_calling,
        config.strip_thinking_tokens,
        _mask_secret(config.llm_api_key),
    )

    # 初始化 MCP 服务器
    try:
        from services.mcp.sync_wrapper import init_mcp_servers
        init_mcp_servers()
        logger.info("MCP servers initialized")
    except Exception as exc:
        logger.warning("MCP initialization failed (non-fatal): %s", exc)

    yield

    # 关闭时执行（目前无需清理）


# 返回 FastAPI 应用实例
def create_app() -> FastAPI:
    app = FastAPI(title="HelloAgents Deep Researcher", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    #app.get是FastAPI的装饰器，用于将函数注册为 HTTP 端点
    #把函数注册为 HTTP 端点 + 自动处理 JSON + 自动生成文档
    #这个function是健康检查接口，用于检查服务是否正常运行
    @app.get("/healthz")
    def health_check() -> Dict[str, str]:
        return {"status": "ok"}

    # 研究接口：同步响应，等待完整研究结果返回
    @app.post("/research", response_model=ResearchResponse)
    def run_research(payload: ResearchRequest) -> ResearchResponse:
        # 构建配置 _build_config(payload) 会根据 payload 中的参数构建一个配置对象
        # 这个配置对象会被 DeepResearchAgent 使用来配置研究代理
        try:
            config = _build_config(payload)
            # 创建 DeepResearchAgent 实例，配置为 payload 中的参数
            # 这个代理会根据配置对象来执行研究任务
            agent = DeepResearchAgent(config=config)
            result = agent.run(payload.topic)
        # 处理 ValueError 异常，通常是配置参数无效
        except ValueError as exc:  # Likely due to unsupported configuration
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        # 处理其他异常，通常是研究任务执行过程中出错
        except Exception as exc:  # pragma: no cover - defensive guardrail
            raise HTTPException(status_code=500, detail="Research failed") from exc
        # 处理研究结果，将 TODO 项转换为 JSON 格式
        todo_payload = [
            {
                "id": item.id,
                "title": item.title,
                "intent": item.intent,
                "query": item.query,
                "status": item.status,
                "summary": item.summary,
                "sources_summary": item.sources_summary,
                "note_id": item.note_id,
                "note_path": item.note_path,
            }
            for item in result.todo_items
        ]
        # 返回研究结果，包含报告和 TODO 项
        # 报告是 Markdown 格式，包含研究任务的详细信息
        # TODO 项是 JSON 格式，包含每个 TODO 项的详细信息
        return ResearchResponse(
            report_markdown=(result.report_markdown or result.running_summary or ""),
            todo_items=todo_payload,
        )
    #这个function是流式研究接口，用于触发研究任务并返回流式结果
    # 这个接口返回一个 EventSourceResponse，包含研究任务的流式结果
    # 流式结果是 JSON 格式，包含研究任务的详细信息
    @app.post("/research/stream")
    async def stream_research(payload: ResearchRequest) -> StreamingResponse:
        # 构建配置 _build_config(payload) 会根据 payload 中的参数构建一个配置对象
        # 这个配置对象会被 DeepResearchAgent 使用来配置研究代理
        try:
            config = _build_config(payload)
            agent = DeepResearchAgent(config=config)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        async def event_iterator():
            try:
                async for event in agent.run_stream_async(payload.topic):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as exc:  # pragma: no cover - defensive guardrail
                logger.exception("Streaming research failed")
                error_payload = {"type": "error", "detail": str(exc)}
                yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
        # 返回流式响应，包含研究任务的流式结果
        # 流式结果是 JSON 格式，包含研究任务的详细信息
        # 流式响应的头信息会告诉浏览器如何处理流式数据
        return StreamingResponse(
            event_iterator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    return app

# 在模块顶层创建 app，而非 if __name__ 块中，以便支持 uvicorn 命令行启动和热更新
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
