import os
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class SearchAPI(Enum):
    ACADEMIC = "academic"
    GOOGLE_SCHOLAR = "google_scholar"
    ARXIV = "arxiv"
    PERPLEXITY = "perplexity"
    TAVILY = "tavily"
    DUCKDUCKGO = "duckduckgo"
    SEARXNG = "searxng"
    ADVANCED = "advanced"


class Configuration(BaseModel):
    """Configuration options for the deep research assistant."""

    max_web_research_loops: int = Field(
        default=3,
        title="Research Depth",
        description="Number of research iterations to perform",
    )
    local_llm: str = Field(
        default="llama3.2",
        title="Local Model Name",
        description="Name of the locally hosted LLM (Ollama/LMStudio)",
    )
    llm_provider: str = Field(
        default="ollama",
        title="LLM Provider",
        description="Provider identifier (ollama, lmstudio, or custom)",
    )
    search_api: SearchAPI = Field(
        default=SearchAPI.ACADEMIC,
        title="Search API",
        description="Web search API to use",
    )
    venue_tiers: list[str] = Field(
        default_factory=list,
        title="Venue Tier Filter",
        description="文献分区筛选（可多选）：ccf_a, ccf_b, ccf_c, jcr_q1~q4, arxiv，空列表表示不限",
    )
    enable_notes: bool = Field(
        default=True,
        title="Enable Notes",
        description="Whether to store task progress in NoteTool",
    )
    notes_workspace: str = Field(
        default="./notes",
        title="Notes Workspace",
        description="Directory for NoteTool to persist task notes",
    )
    fetch_full_page: bool = Field(
        default=True,
        title="Fetch Full Page",
        description="Include the full page content in the search results",
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        title="Ollama Base URL",
        description="Base URL for Ollama API (without /v1 suffix)",
    )
    lmstudio_base_url: str = Field(
        default="http://localhost:1234/v1",
        title="LMStudio Base URL",
        description="Base URL for LMStudio OpenAI-compatible API",
    )
    strip_thinking_tokens: bool = Field(
        default=True,
        title="Strip Thinking Tokens",
        description="Whether to strip <think> tokens from model responses",
    )
    use_tool_calling: bool = Field(
        default=False,
        title="Use Tool Calling",
        description="Use tool calling instead of JSON mode for structured output",
    )
    llm_api_key: Optional[str] = Field(
        default=None,
        title="LLM API Key",
        description="Optional API key when using custom OpenAI-compatible services",
    )
    llm_base_url: Optional[str] = Field(
        default=None,
        title="LLM Base URL",
        description="Optional base URL when using custom OpenAI-compatible services",
    )
    llm_model_id: Optional[str] = Field(
        default=None,
        title="LLM Model ID",
        description="Optional model identifier for custom OpenAI-compatible services",
    )
    enable_zotero: bool = Field(
        default=False,
        title="Enable Zotero",
        description="Whether to auto-import papers to Zotero",
    )
    zotero_library_id: Optional[str] = Field(
        default=None,
        title="Zotero Library ID",
        description="Zotero library ID for literature management",
    )
    zotero_api_key: Optional[str] = Field(
        default=None,
        title="Zotero API Key",
        description="Zotero API key for authentication",
    )
    zotero_library_type: str = Field(
        default="user",
        title="Zotero Library Type",
        description="Zotero library type (user or group)",
    )
    enable_rag: bool = Field(
        default=True,
        title="Enable RAG",
        description="Whether to use RAG vector retrieval to augment context",
    )
    rag_collection_name: str = Field(
        default="deep_research",
        title="RAG Collection Name",
        description="ChromaDB collection name for vector storage",
    )
    enable_camel_review: bool = Field(
        default=False,
        title="Enable CAMEL Review",
        description="Whether to use CAMEL Researcher-Reviewer dialogue for quality review",
    )
    camel_max_review_rounds: int = Field(
        default=3,
        title="CAMEL Max Review Rounds",
        description="Maximum number of Researcher-Reviewer dialogue rounds",
    )
    pdf_dir: str = Field(
        default="",
        title="PDF Directory",
        description="Directory to store downloaded PDF files",
    )
    papers_per_task: int = Field(
        default=10,
        title="Papers Per Task",
        description="Number of papers to search per sub-task",
    )
    max_pdf_downloads: int = Field(
        default=5,
        title="Max PDF Downloads",
        description="Maximum number of PDFs to download per sub-task",
    )
    enable_pdf_download: bool = Field(
        default=True,
        title="Enable PDF Download",
        description="Whether to automatically download PDF files",
    )

    @classmethod
    def from_env(cls, overrides: Optional[dict[str, Any]] = None) -> "Configuration":
        """Create a configuration object using environment variables and overrides."""

        raw_values: dict[str, Any] = {}

        # Load values from environment variables based on field names
        for field_name in cls.model_fields.keys():
            env_key = field_name.upper()
            if env_key in os.environ:
                raw_values[field_name] = os.environ[env_key]

        # Additional mappings for explicit env names
        env_aliases = {
            "local_llm": os.getenv("LOCAL_LLM"),
            "llm_provider": os.getenv("LLM_PROVIDER"),
            "llm_api_key": os.getenv("LLM_API_KEY"),
            "llm_model_id": os.getenv("LLM_MODEL_ID"),
            "llm_base_url": os.getenv("LLM_BASE_URL"),
            "lmstudio_base_url": os.getenv("LMSTUDIO_BASE_URL"),
            "ollama_base_url": os.getenv("OLLAMA_BASE_URL"),
            "max_web_research_loops": os.getenv("MAX_WEB_RESEARCH_LOOPS"),
            "fetch_full_page": os.getenv("FETCH_FULL_PAGE"),
            "strip_thinking_tokens": os.getenv("STRIP_THINKING_TOKENS"),
            "use_tool_calling": os.getenv("USE_TOOL_CALLING"),
            "search_api": os.getenv("SEARCH_API"),
            "enable_notes": os.getenv("ENABLE_NOTES"),
            "notes_workspace": os.getenv("NOTES_WORKSPACE"),
            "enable_zotero": os.getenv("ENABLE_ZOTERO"),
            "zotero_library_id": os.getenv("ZOTERO_LIBRARY_ID"),
            "zotero_api_key": os.getenv("ZOTERO_API_KEY"),
            "zotero_library_type": os.getenv("ZOTERO_LIBRARY_TYPE"),
            "enable_rag": os.getenv("ENABLE_RAG"),
            "rag_collection_name": os.getenv("RAG_COLLECTION_NAME"),
            "enable_camel_review": os.getenv("ENABLE_CAMEL_REVIEW"),
            "camel_max_review_rounds": os.getenv("CAMEL_MAX_REVIEW_ROUNDS"),
            "venue_tiers": os.getenv("VENUE_TIERS"),
            "pdf_dir": os.getenv("PDF_DIR"),
            "papers_per_task": os.getenv("PAPERS_PER_TASK"),
            "max_pdf_downloads": os.getenv("MAX_PDF_DOWNLOADS"),
            "enable_pdf_download": os.getenv("ENABLE_PDF_DOWNLOAD"),
        }

        for key, value in env_aliases.items():
            if value is not None:
                raw_values.setdefault(key, value)

        if overrides:
            for key, value in overrides.items():
                if value is not None:
                    raw_values[key] = value

        # 处理 venue_tiers：逗号分隔的字符串转为列表
        if "venue_tiers" in raw_values:
            vt = raw_values["venue_tiers"]
            if isinstance(vt, str):
                raw_values["venue_tiers"] = [t.strip() for t in vt.split(",") if t.strip()]

        # 处理整数类型的环境变量
        int_fields = ["papers_per_task", "max_pdf_downloads", "max_web_research_loops",
                       "camel_max_review_rounds"]
        for field in int_fields:
            if field in raw_values and isinstance(raw_values[field], str):
                try:
                    raw_values[field] = int(raw_values[field])
                except ValueError:
                    pass

        # 处理布尔类型的环境变量
        bool_fields = ["enable_pdf_download", "enable_zotero", "enable_rag",
                       "enable_notes", "enable_camel_review", "fetch_full_page",
                       "strip_thinking_tokens", "use_tool_calling"]
        for field in bool_fields:
            if field in raw_values and isinstance(raw_values[field], str):
                raw_values[field] = raw_values[field].lower() in ("true", "1", "yes")

        return cls(**raw_values)

    def sanitized_ollama_url(self) -> str:
        """Ensure Ollama base URL includes the /v1 suffix required by OpenAI clients."""

        base = self.ollama_base_url.rstrip("/")
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        return base

    def resolved_model(self) -> Optional[str]:
        """Best-effort resolution of the model identifier to use."""

        return self.llm_model_id or self.local_llm

