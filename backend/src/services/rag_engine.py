"""RAG engine for vector indexing and semantic retrieval via ChromaDB."""

from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# Chunking parameters
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64


class RAGEngine:
    """Vector store backed by ChromaDB with sentence-transformers embeddings."""

    def __init__(self, collection_name: str = "deep_research") -> None:
        import chromadb

        self._client = chromadb.PersistentClient(path="./vector_db")
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "RAG collection '%s' ready (%d existing chunks)",
            collection_name,
            self._collection.count(),
        )

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def ingest_search_results(
        self,
        task_id: int,
        search_result: dict[str, Any],
        run_id: str | None = None,
    ) -> int:
        """Chunk and index search result content into the vector store.

        Returns the number of chunks added.
        """
        results = search_result.get("results", [])
        if not results:
            return 0

        all_ids: list[str] = []
        all_documents: list[str] = []
        all_metadatas: list[dict[str, Any]] = []

        for item in results:
            title = item.get("title", "")
            url = item.get("url", "")
            content = item.get("content", "")
            raw_content = item.get("raw_content", "")

            # Build full text for this source
            parts = [title]
            if content:
                parts.append(content)
            if raw_content:
                parts.append(raw_content)
            full_text = "\n\n".join(p for p in parts if p)

            if not full_text.strip():
                continue

            # Chunk
            chunks = self._chunk_text(full_text, CHUNK_SIZE, CHUNK_OVERLAP)
            for i, chunk in enumerate(chunks):
                chunk_id = f"task{task_id}_{uuid.uuid4().hex[:8]}_{i}"
                all_ids.append(chunk_id)
                all_documents.append(chunk)
                metadata: dict[str, Any] = {
                    "task_id": task_id,
                    "source_title": title[:200],
                    "source_url": url[:500],
                    "chunk_index": i,
                }
                if run_id:
                    metadata["run_id"] = run_id
                all_metadatas.append(metadata)

        if not all_ids:
            return 0

        # Batch upsert (ChromaDB handles large batches)
        batch_size = 256
        for start in range(0, len(all_ids), batch_size):
            end = start + batch_size
            self._collection.upsert(
                ids=all_ids[start:end],
                documents=all_documents[start:end],
                metadatas=all_metadatas[start:end],
            )

        logger.info(
            "RAG indexed %d chunks from %d sources for task %d",
            len(all_ids),
            len(results),
            task_id,
        )
        return len(all_ids)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def query(
        self,
        question: str,
        top_k: int = 5,
        task_id: int | None = None,
        run_id: str | None = None,
    ) -> str:
        """Semantic search for the most relevant chunks.

        Returns concatenated text separated by delimiters, or empty string
        if nothing is found.
        """
        if self._collection.count() == 0:
            return ""

        query_kwargs: dict[str, Any] = {
            "query_texts": [question],
            "n_results": min(top_k, self._collection.count()),
        }
        if task_id is not None and run_id:
            query_kwargs["where"] = {
                "$and": [{"task_id": task_id}, {"run_id": run_id}]
            }
        elif task_id is not None:
            query_kwargs["where"] = {"task_id": task_id}
        elif run_id:
            query_kwargs["where"] = {"run_id": run_id}

        results = self._collection.query(**query_kwargs)

        documents = results.get("documents", [[]])[0]
        if not documents:
            return ""

        return "\n\n---\n\n".join(documents)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
        """Split text into overlapping chunks by character count."""
        if len(text) <= chunk_size:
            return [text]

        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk)
            start += chunk_size - overlap

        return chunks
