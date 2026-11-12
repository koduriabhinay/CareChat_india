"""Trusted reference content and search over it.

The MVP uses SQLite full-text search (BM25 ranking) so it runs with no extra
services. The interface is small on purpose: swapping in PostgreSQL with
pgvector later only means reimplementing `add_document` and `search`.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from dataclasses import dataclass

_WORD_RE = re.compile(r"[A-Za-z0-9]+")
# Common words that add noise to keyword search.
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "can", "do", "does", "for", "from", "how", "i",
    "if", "in", "is", "it", "me", "my", "of", "on", "or", "should", "so", "that", "the", "this",
    "to", "was", "what", "when", "which", "why", "will", "with", "you", "your", "mean", "means",
}


@dataclass(frozen=True)
class Passage:
    title: str
    url: str
    text: str


def chunk_text(text: str, max_chars: int = 1200) -> list[str]:
    """Split text into chunks on paragraph boundaries."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if current and len(current) + len(para) + 2 > max_chars:
            chunks.append(current)
            current = ""
        current = f"{current}\n\n{para}" if current else para
        while len(current) > max_chars:
            chunks.append(current[:max_chars])
            current = current[max_chars:]
    if current:
        chunks.append(current)
    return chunks


def _fts_query(question: str) -> str | None:
    words = [w.lower() for w in _WORD_RE.findall(question)]
    terms = [w for w in words if w not in _STOPWORDS and len(w) > 1]
    if not terms:
        return None
    # OR the terms together so partial matches still rank; quote each to avoid FTS syntax.
    return " OR ".join(f'"{t}"' for t in dict.fromkeys(terms))


class KnowledgeBase:
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(title, url UNINDEXED, body)"
            )
            self._conn.commit()

    def add_document(self, title: str, url: str, text: str) -> int:
        """Index a reference page, replacing any earlier copy of the same URL."""
        chunks = chunk_text(text)
        with self._lock:
            self._conn.execute("DELETE FROM passages WHERE url = ?", (url,))
            self._conn.executemany(
                "INSERT INTO passages (title, url, body) VALUES (?, ?, ?)",
                [(title, url, c) for c in chunks],
            )
            self._conn.commit()
        return len(chunks)

    def count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT count(*) FROM passages").fetchone()[0]

    def search(self, question: str, k: int = 4) -> list[Passage]:
        query = _fts_query(question)
        if query is None:
            return []
        with self._lock:
            rows = self._conn.execute(
                "SELECT title, url, body FROM passages WHERE passages MATCH ? ORDER BY bm25(passages) LIMIT ?",
                (query, k),
            ).fetchall()
        return [Passage(title=t, url=u, text=b) for t, u, b in rows]
