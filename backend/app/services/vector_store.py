"""
ChromaDB wrapper for semantic retrieval over transaction descriptions.
Uses ChromaDB's ONNX embedding model for local embeddings.
"""
from __future__ import annotations

import chromadb
from loguru import logger

from backend.app.config import settings

# Import the ONNX embedding function — path varies between chromadb 0.5.x and 1.x.
# Fall back to DefaultEmbeddingFunction if neither path resolves.
_EF = None
try:
    from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2 as _EF  # type: ignore
except (ImportError, AttributeError):
    pass

if _EF is None:
    try:
        from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2 as _EF  # type: ignore
    except (ImportError, AttributeError):
        pass

if _EF is None:
    try:
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction as _EF  # type: ignore
        logger.warning("ONNXMiniLM_L6_V2 not found; using chromadb DefaultEmbeddingFunction.")
    except (ImportError, AttributeError):
        _EF = None
        logger.warning("No chromadb embedding function could be imported; vector search disabled.")

_client: chromadb.ClientAPI | None = None
_collection: chromadb.Collection | None = None

_COLLECTION_NAME = "transactions"


def _get_collection() -> chromadb.Collection:
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=settings.chroma_path)
        ef = _EF() if _EF is not None else None
        kwargs: dict = {"name": _COLLECTION_NAME, "metadata": {"hnsw:space": "cosine"}}
        if ef is not None:
            kwargs["embedding_function"] = ef
        _collection = _client.get_or_create_collection(**kwargs)
        logger.info(f"ChromaDB collection ready: {_COLLECTION_NAME}")
    return _collection


def upsert_transactions(
    ids: list[str],
    documents: list[str],
    metadatas: list[dict],
) -> None:
    col = _get_collection()
    col.upsert(ids=ids, documents=documents, metadatas=metadatas)
    logger.debug(f"Upserted {len(ids)} transactions to vector store")


def query_similar(
    query: str,
    user_id: str = "demo",
    n_results: int = 10,
) -> list[dict]:
    try:
        col = _get_collection()
        results = col.query(
            query_texts=[query],
            n_results=n_results,
            where={"user_id": user_id},
        )
        if not results["documents"] or not results["documents"][0]:
            return []
        docs = results["documents"][0]
        metas = results["metadatas"][0] if results["metadatas"] else [{}] * len(docs)
        return [{"document": d, "metadata": m} for d, m in zip(docs, metas)]
    except Exception as exc:
        logger.warning(f"Vector search failed (non-fatal): {exc}")
        return []


def reset_user_data(user_id: str = "demo") -> None:
    try:
        col = _get_collection()
        col.delete(where={"user_id": user_id})
        logger.info(f"Cleared vector store for user_id={user_id}")
    except Exception as exc:
        logger.warning(f"Vector reset failed (non-fatal): {exc}")
