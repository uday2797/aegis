"""
AEGIS Knowledge Store
Vector-based incident memory using ChromaDB.
Enables AEGIS to learn from past incidents and retrieve similar cases during RCA.
Falls back to in-memory storage if ChromaDB is not available.
"""
import hashlib
import math
import uuid
from datetime import datetime
from typing import List
from loguru import logger

from src.models import DetectedIncident, RCAResult, HealResult


# ─── Lightweight embedding — no model download needed ────────────────────────

def _make_embedding_function():
    """
    Returns a ChromaDB-compatible EmbeddingFunction that uses keyword-hash
    vectors. Zero external dependencies, no download. Works well for
    structured incident text (failure type, root cause, action keywords).
    """
    try:
        import chromadb
        from chromadb.api.types import Documents, Embeddings

        class _LightweightEF(chromadb.EmbeddingFunction[Documents]):
            def __init__(self):
                pass

            def __call__(self, input: Documents) -> Embeddings:  # noqa: A002
                result = []
                for text in input:
                    vec = [0.0] * 256
                    for tok in text.lower().split():
                        h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
                        vec[h % 256] += 1.0
                        # bigram prefix for better recall
                        if len(tok) > 3:
                            h2 = int(hashlib.md5(tok[:4].encode()).hexdigest(), 16)
                            vec[h2 % 256] += 0.5
                    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
                    result.append([x / norm for x in vec])
                return result

            @staticmethod
            def name() -> str:
                return "aegis_lightweight_v1"

            def get_config(self) -> dict:
                return {}

            @staticmethod
            def build_from_config(config: dict) -> "_LightweightEF":
                return _LightweightEF()

        return _LightweightEF()
    except Exception:
        return None

class IncidentKnowledgeStore:
    """
    Stores resolved incidents as vector embeddings for semantic retrieval.
    When a new incident occurs, AEGIS retrieves the top-k most similar
    past incidents to enrich the LLM RCA context.
    """

    def __init__(self, config: dict):
        self.persist_dir = config.get("persist_dir", "./data/knowledge_store")
        self.collection_name = config.get("collection_name", "aegis_incidents")
        self._collection = None
        self._fallback: List[dict] = []  # in-memory fallback
        self._init_store()

    def _init_store(self):
        try:
            import chromadb
            ef = _make_embedding_function()
            client = chromadb.PersistentClient(path=self.persist_dir)
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
                embedding_function=ef,
            )
            logger.info(f"[KNOWLEDGE] ChromaDB initialized at {self.persist_dir} (lightweight embeddings, no download)")
        except ImportError:
            logger.warning("[KNOWLEDGE] ChromaDB not installed — using in-memory fallback")
        except Exception as e:
            logger.warning(f"[KNOWLEDGE] ChromaDB init failed: {e} — using in-memory fallback")

    async def store(self, incident: DetectedIncident, rca: RCAResult, heal: HealResult):
        """Persists a resolved incident for future retrieval."""
        doc_text = (
            f"Incident: {incident.job_name} | "
            f"Failure: {rca.failure_type.value} | "
            f"Root Cause: {rca.root_cause} | "
            f"Action: {heal.action_taken} | "
            f"Outcome: {heal.outcome}"
        )
        metadata = {
            "incident_id": incident.incident_id,
            "job_name": incident.job_name,
            "failure_type": rca.failure_type.value,
            "root_cause": rca.root_cause,
            "action_taken": heal.action_taken,
            "outcome": heal.outcome,
            "auto_healed": str(heal.status.value == "auto_healed"),
            "timestamp": incident.timestamp.isoformat(),
        }

        if self._collection:
            self._collection.add(
                documents=[doc_text],
                metadatas=[metadata],
                ids=[f"{incident.incident_id}_{uuid.uuid4().hex[:6]}"],
            )
        else:
            self._fallback.append({"text": doc_text, "metadata": metadata})

        logger.info(f"[KNOWLEDGE] Stored incident {incident.incident_id}")

    async def find_similar(self, query: str, k: int = 5) -> List[str]:
        """Retrieves top-k similar past incidents based on semantic similarity."""
        if self._collection:
            try:
                results = self._collection.query(query_texts=[query], n_results=min(k, self._collection.count()))
                docs = results.get("documents", [[]])[0]
                metas = results.get("metadatas", [[]])[0]
                summaries = []
                for doc, meta in zip(docs, metas):
                    summaries.append(
                        f"[Past Incident {meta.get('incident_id', 'N/A')}] "
                        f"{meta.get('failure_type', '')} on {meta.get('job_name', '')} — "
                        f"Root cause: {meta.get('root_cause', '')} — "
                        f"Fixed by: {meta.get('action_taken', '')}"
                    )
                return summaries
            except Exception as e:
                logger.warning(f"[KNOWLEDGE] Query failed: {e}")

        # Fallback: simple keyword match
        matched = []
        query_lower = query.lower()
        for record in self._fallback[-20:]:
            if any(word in record["text"].lower() for word in query_lower.split()[:3]):
                meta = record["metadata"]
                matched.append(
                    f"[Past Incident {meta.get('incident_id', 'N/A')}] "
                    f"{meta.get('root_cause', '')} → {meta.get('action_taken', '')}"
                )
        return matched[:k]
