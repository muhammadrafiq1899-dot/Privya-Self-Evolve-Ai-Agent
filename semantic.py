"""
semantic.py – Semantic vector search for RAG and memory retrieval.

Uses local sentence-transformers for embeddings with sqlite-vec or numpy
for vector storage. Enables conceptual search beyond keyword matching.

Fallback: If sentence-transformers is unavailable, uses a simple TF-IDF approach.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import struct
from collections import Counter
from pathlib import Path
from typing import Any, Optional

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    np = None
    HAS_NUMPY = False

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.getenv("AGENT_DATA_DIR", Path.home() / ".ai-agent"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

VECTOR_DB_PATH = DATA_DIR / "vectors.db"
EMBEDDINGS_CACHE = DATA_DIR / "embeddings_cache.json"

# Model configuration
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_DIM = 384  # MiniLM-L6-v2 dimension

# ---------------------------------------------------------------------------
# Embedding backends
# ---------------------------------------------------------------------------

_model = None


def _get_model():
    """Lazy-load sentence-transformers model."""
    global _model
    if _model is not None:
        return _model
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(EMBEDDING_MODEL)
        return _model
    except ImportError:
        return None
    except Exception:
        return None


def get_embedding(text: str) -> list[float]:
    """Get embedding vector for text.

    Uses sentence-transformers if available, otherwise TF-IDF fallback.
    """
    model = _get_model()
    if model is not None:
        embedding = model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    # TF-IDF fallback
    return _tfidf_embedding(text)


def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Get embeddings for multiple texts."""
    model = _get_model()
    if model is not None:
        embeddings = model.encode(texts, normalize_embeddings=True, batch_size=32)
        return embeddings.tolist()
    return [_tfidf_embedding(t) for t in texts]


# ---------------------------------------------------------------------------
# TF-IDF fallback embedding
# ---------------------------------------------------------------------------

# Simple vocabulary for TF-IDF
_vocab: dict[str, int] = {}
_idf: dict[str, float] = {}


def _tokenize(text: str) -> list[str]:
    """Simple tokenization."""
    import re
    return re.findall(r'\b[a-z0-9]+\b', text.lower())


def _tfidf_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Generate a fixed-dimension embedding using TF-IDF hashing."""
    tokens = _tokenize(text)
    if not tokens:
        return [0.0] * dim

    # Hash tokens to fixed dimensions
    vec = [0.0] * dim
    counts = Counter(tokens)
    total = len(tokens)

    for token, count in counts.items():
        # Hash token to dimension index
        idx = hash(token) % dim
        tf = count / total
        # Simple IDF approximation
        idf = math.log(1000 / (1 + hash(token) % 100))
        vec[idx] += tf * idf

    # Normalize
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]

    return vec


# ---------------------------------------------------------------------------
# Vector storage (sqlite + numpy)
# ---------------------------------------------------------------------------

class VectorStore:
    """SQLite-backed vector store with numpy similarity search."""

    def __init__(self, db_path: Path = VECTOR_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the vector database."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vectors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                metadata TEXT,
                vector BLOB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_created ON vectors(created_at)
        """)
        conn.commit()
        conn.close()

    def _vector_to_blob(self, vector: list[float]) -> bytes:
        """Convert vector to binary blob."""
        return struct.pack(f'{len(vector)}f', *vector)

    def _blob_to_vector(self, blob: bytes) -> list[float]:
        """Convert binary blob to vector list."""
        n = len(blob) // 4
        return list(struct.unpack(f'{n}f', blob))

    def add(self, text: str, metadata: dict[str, Any] | None = None) -> int:
        """Add a text entry with its embedding vector."""
        vector = get_embedding(text)
        blob = self._vector_to_blob(vector)
        meta_json = json.dumps(metadata) if metadata else None

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute(
            "INSERT INTO vectors (text, metadata, vector) VALUES (?, ?, ?)",
            (text, meta_json, blob),
        )
        row_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return row_id

    def add_batch(self, entries: list[dict[str, Any]]) -> list[int]:
        """Add multiple entries at once."""
        texts = [e["text"] for e in entries]
        vectors = get_embeddings_batch(texts)

        conn = sqlite3.connect(str(self.db_path))
        ids = []
        for entry, vector in zip(entries, vectors):
            blob = self._vector_to_blob(vector)
            meta_json = json.dumps(entry.get("metadata")) if entry.get("metadata") else None
            cursor = conn.execute(
                "INSERT INTO vectors (text, metadata, vector) VALUES (?, ?, ?)",
                (entry["text"], meta_json, blob),
            )
            ids.append(cursor.lastrowid)
        conn.commit()
        conn.close()
        return ids

    def search(self, query: str, limit: int = 10, threshold: float = 0.3) -> list[dict[str, Any]]:
        """Semantic search using cosine similarity.

        Returns entries sorted by similarity score.
        """
        query_vec = get_embedding(query)

        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute("SELECT id, text, metadata, vector FROM vectors").fetchall()
        conn.close()

        if not rows:
            return []

        results = []
        query_norm = math.sqrt(sum(x * x for x in query_vec))

        for row_id, text, meta_json, blob in rows:
            vec = self._blob_to_vector(blob)
            # Cosine similarity using pure Python
            dot = sum(a * b for a, b in zip(query_vec, vec))
            vec_norm = math.sqrt(sum(x * x for x in vec))
            score = dot / (query_norm * vec_norm) if (query_norm * vec_norm) > 0 else 0.0

            if score >= threshold:
                metadata = json.loads(meta_json) if meta_json else {}
                results.append({
                    "id": row_id,
                    "text": text,
                    "score": score,
                    "metadata": metadata,
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def delete(self, entry_id: int) -> bool:
        """Delete an entry by ID."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute("DELETE FROM vectors WHERE id = ?", (entry_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        return deleted

    def count(self) -> int:
        """Get total number of entries."""
        conn = sqlite3.connect(str(self.db_path))
        count = conn.execute("SELECT COUNT(*) FROM vectors").fetchone()[0]
        conn.close()
        return count

    def rebuild_index(self) -> dict[str, Any]:
        """Rebuild all embeddings (useful after model changes)."""
        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute("SELECT id, text FROM vectors").fetchall()

        if not rows:
            conn.close()
            return {"status": "empty", "rebuilt": 0}

        texts = [r[1] for r in rows]
        vectors = get_embeddings_batch(texts)

        for (row_id, _), vector in zip(rows, vectors):
            blob = self._vector_to_blob(vector)
            conn.execute("UPDATE vectors SET vector = ? WHERE id = ?", (blob, row_id))

        conn.commit()
        conn.close()
        return {"status": "completed", "rebuilt": len(rows)}


# ---------------------------------------------------------------------------
# Obsidian vault indexing
# ---------------------------------------------------------------------------

class ObsidianIndexer:
    """Index Obsidian vault notes for semantic search."""

    def __init__(self, store: VectorStore):
        self.store = store

    def index_vault(self, vault_path: str) -> dict[str, Any]:
        """Index all markdown files in an Obsidian vault."""
        vault = Path(vault_path).expanduser().resolve()
        if not vault.exists():
            return {"error": f"Vault not found: {vault_path}"}

        md_files = list(vault.rglob("*.md"))
        if not md_files:
            return {"status": "empty", "indexed": 0}

        entries = []
        for f in md_files:
            try:
                content = f.read_text(encoding="utf-8")
                # Split into chunks of ~500 chars for better search
                chunks = _chunk_text(content, max_chars=500, overlap=100)
                rel_path = str(f.relative_to(vault))

                for i, chunk in enumerate(chunks):
                    if chunk.strip():
                        entries.append({
                            "text": chunk.strip(),
                            "metadata": {
                                "source": "obsidian",
                                "file": rel_path,
                                "chunk_index": i,
                            },
                        })
            except (UnicodeDecodeError, OSError):
                continue

        if entries:
            self.store.add_batch(entries)

        return {"status": "completed", "indexed": len(entries), "files": len(md_files)}

    def search_vault(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search indexed vault notes semantically."""
        results = self.store.search(query, limit=limit, threshold=0.2)
        return [r for r in results if r.get("metadata", {}).get("source") == "obsidian"]


# ---------------------------------------------------------------------------
# Text chunking utility
# ---------------------------------------------------------------------------

def _chunk_text(text: str, max_chars: int = 500, overlap: int = 100) -> list[str]:
    """Split text into overlapping chunks."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        # Try to break at a sentence or paragraph
        if end < len(text):
            for sep in ["\n\n", "\n", ". ", "! ", "? "]:
                last_sep = text.rfind(sep, start + max_chars // 2, end)
                if last_sep > start:
                    end = last_sep + len(sep)
                    break
        chunks.append(text[start:end])
        start = end - overlap

    return chunks


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

vector_store = VectorStore()
obsidian_indexer = ObsidianIndexer(vector_store)


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

SEMANTIC_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "semantic_search",
            "description": "Search through memories and notes using conceptual meaning, not just keywords. Great for finding related information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for (conceptual or specific)"},
                    "limit": {"type": "integer", "description": "Max results (default 10)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "index_obsidian_vault",
            "description": "Index all notes in the Obsidian vault for semantic search.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vault_path": {"type": "string", "description": "Path to Obsidian vault"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_obsidian",
            "description": "Search Obsidian vault notes semantically (conceptual meaning search).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for"},
                    "limit": {"type": "integer", "description": "Max results (default 5)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_knowledge",
            "description": "Add text to the semantic knowledge base for future retrieval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to add"},
                    "source": {"type": "string", "description": "Source label (e.g. 'note', 'research', 'conversation')"},
                },
                "required": ["text"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def semantic_search(query: str, limit: int = 10) -> dict[str, Any]:
    """Search the semantic knowledge base."""
    results = vector_store.search(query, limit=limit, threshold=0.2)
    if not results:
        return {"result": "No semantically similar results found."}

    lines = []
    for i, r in enumerate(results, 1):
        score_pct = int(r["score"] * 100)
        source = r.get("metadata", {}).get("source", "unknown")
        lines.append(f"{i}. [{score_pct}% match, {source}] {r['text'][:200]}")
    return {"result": "\n".join(lines)}


async def index_obsidian_vault(vault_path: str | None = None) -> dict[str, Any]:
    """Index the Obsidian vault for semantic search."""
    if not vault_path:
        vault_path = os.getenv("OBSIDIAN_VAULT", "~/ai-agent/vault")
    return {"result": obsidian_indexer.index_vault(vault_path)}


async def search_obsidian(query: str, limit: int = 5) -> dict[str, Any]:
    """Search Obsidian notes semantically."""
    results = obsidian_indexer.search_vault(query, limit=limit)
    if not results:
        return {"result": "No matching Obsidian notes found."}

    lines = []
    for i, r in enumerate(results, 1):
        score_pct = int(r["score"] * 100)
        filename = r.get("metadata", {}).get("file", "unknown")
        lines.append(f"{i}. [{score_pct}%] {filename}: {r['text'][:150]}")
    return {"result": "\n".join(lines)}


async def add_to_knowledge(text: str, source: str = "conversation") -> dict[str, Any]:
    """Add text to the semantic knowledge base."""
    entry_id = vector_store.add(text, metadata={"source": source})
    return {"result": f"Added to knowledge base (id: {entry_id})"}


SEMANTIC_TOOL_MAP = {
    "semantic_search": semantic_search,
    "index_obsidian_vault": index_obsidian_vault,
    "search_obsidian": search_obsidian,
    "add_to_knowledge": add_to_knowledge,
}
