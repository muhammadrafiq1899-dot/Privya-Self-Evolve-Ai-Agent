"""
memory.py – Three-tier memory system.

1. **ShortTerm**   – In-memory rolling buffer (working memory).
2. **LongTerm**    – JSONL file store with optional Obsidian sync.
3. **Procedural**  – Learned tool-use procedures / skills.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.getenv("AGENT_DATA_DIR", Path.home() / ".ai-agent"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

LONG_TERM_PATH = DATA_DIR / "long_term.jsonl"
PROCEDURAL_PATH = DATA_DIR / "procedural.jsonl"
PROCEDURES_INDEX = DATA_DIR / "procedures_index.json"


# ---------------------------------------------------------------------------
# Short-term (working) memory
# ---------------------------------------------------------------------------

@dataclass
class ShortTerm:
    """Fixed-size rolling conversation buffer."""

    max_turns: int = 40
    messages: list[dict[str, Any]] = field(default_factory=list)

    def add(self, msg: dict[str, Any]) -> None:
        self.messages.append(msg)
        if len(self.messages) > self.max_turns * 2:
            self.messages = self.messages[-self.max_turns * 2:]

    def snapshot(self) -> list[dict[str, Any]]:
        return list(self.messages)

    def clear(self) -> None:
        self.messages.clear()


# ---------------------------------------------------------------------------
# Long-term memory
# ---------------------------------------------------------------------------

@dataclass
class MemoryEntry:
    text: str
    timestamp: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)
    source: str = "conversation"
    importance: float = 0.5  # 0-1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MemoryEntry":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class LongTerm:
    """Append-only JSONL store with keyword search."""

    def __init__(self, path: Path = LONG_TERM_PATH):
        self.path = path
        self._cache: list[MemoryEntry] | None = None

    def _load_all(self) -> list[MemoryEntry]:
        if self._cache is not None:
            return self._cache
        entries: list[MemoryEntry] = []
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        entries.append(MemoryEntry.from_dict(json.loads(line)))
                    except (json.JSONDecodeError, TypeError):
                        continue
        self._cache = entries
        return entries

    def add(self, entry: MemoryEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        self._cache = None  # invalidate

    def search(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        """Simple keyword search across all entries."""
        query_lower = query.lower()
        keywords = query_lower.split()
        scored: list[tuple[float, MemoryEntry]] = []
        for e in self._load_all():
            text_lower = e.text.lower()
            hits = sum(1 for kw in keywords if kw in text_lower)
            if hits:
                scored.append((hits * e.importance, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:limit]]

    def recent(self, n: int = 20) -> list[MemoryEntry]:
        return self._load_all()[-n:]


# ---------------------------------------------------------------------------
# Procedural memory (learned skills)
# ---------------------------------------------------------------------------

@dataclass
class Procedure:
    name: str
    description: str
    steps: list[str]
    tool_pattern: str  # e.g. "run_python → summarize"
    success_count: int = 0
    last_used: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Procedure":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class ProceduralMemory:
    """Stores learned multi-step procedures derived from successful trajectories."""

    def __init__(self, path: Path = PROCEDURAL_PATH, index_path: Path = PROCEDURES_INDEX):
        self.path = path
        self.index_path = index_path
        self._procedures: list[Procedure] | None = None
        self._index: dict[str, int] | None = None

    def _load(self) -> list[Procedure]:
        if self._procedures is not None:
            return self._procedures
        procs: list[Procedure] = []
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        procs.append(Procedure.from_dict(json.loads(line)))
                    except (json.JSONDecodeError, TypeError):
                        continue
        self._procedures = procs
        return procs

    def _load_index(self) -> dict[str, int]:
        if self._index is not None:
            return self._index
        if self.index_path.exists():
            try:
                self._index = json.loads(self.index_path.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                self._index = {}
        else:
            self._index = {}
        return self._index or {}

    def add(self, proc: Procedure) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(proc.to_dict(), ensure_ascii=False) + "\n")
        idx = self._load_index()
        idx[proc.name] = len(self._load())
        self.index_path.write_text(json.dumps(idx, indent=2), "utf-8")
        self._procedures = None
        self._index = None

    def find(self, query: str) -> list[Procedure]:
        """Keyword match against procedure names and descriptions."""
        q = query.lower()
        return [
            p for p in self._load()
            if q in p.name.lower() or q in p.description.lower()
            or any(q in s.lower() for s in p.steps)
        ]

    def get(self, name: str) -> Procedure | None:
        idx = self._load_index()
        pos = idx.get(name)
        if pos is not None:
            procs = self._load()
            if pos < len(procs):
                return procs[pos]
        return None

    def all_procedures(self) -> list[Procedure]:
        return self._load()


# ---------------------------------------------------------------------------
# Convenience singletons
# ---------------------------------------------------------------------------

short_term = ShortTerm()
long_term = LongTerm()
procedural = ProceduralMemory()
