"""Scalable knowledge store (SQLite now; designed for growth)."""
from __future__ import annotations
import hashlib
import json
import re
import time
from typing import Any

# Capacity targets (configured limits; actual scale depends on server/database resources)
MAX_KB_DOCUMENTS = 10_000_000
MAX_DOCUMENT_CHARS = 1_000_000_000

# lexical search helpers — no external vector DB required for v1

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def chunk_text(text: str, size: int = 800, overlap: int = 120) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks = []
    i = 0
    n = len(text)
    while i < n:
        chunks.append(text[i : i + size])
        i += max(size - overlap, 1)
    return chunks


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def ensure_knowledge_tables(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS kb_documents (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            source TEXT,
            lang TEXT,
            content_hash TEXT NOT NULL UNIQUE,
            bytes INTEGER,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS kb_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            token_approx INTEGER,
            FOREIGN KEY(doc_id) REFERENCES kb_documents(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_kb_chunks_doc ON kb_chunks(doc_id);
        CREATE INDEX IF NOT EXISTS idx_kb_docs_hash ON kb_documents(content_hash);
        CREATE TABLE IF NOT EXISTS purchase_requests (
            id TEXT PRIMARY KEY,
            user_key TEXT NOT NULL,
            plan_id TEXT NOT NULL,
            plan_name TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            note TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_purchase_user ON purchase_requests(user_key);
        """
    )


def ingest_document(conn, title: str, content: str, source: str = "", lang: str = "fa") -> dict[str, Any]:
    title = (title or "بدون عنوان").strip()[:200]
    content = (content or "").strip()
    if len(content) < 10:
        raise ValueError("متن سند خیلی کوتاه است.")
    if len(content) > MAX_DOCUMENT_CHARS:
        raise ValueError("حجم سند بیش از حد مجاز است.")
    h = content_hash(content)
    existing = conn.execute("SELECT id, title FROM kb_documents WHERE content_hash=?", (h,)).fetchone()
    if existing:
        return {"ok": True, "duplicate": True, "id": existing["id"], "title": existing["title"]}
    count_row = conn.execute("SELECT COUNT(*) AS c FROM kb_documents").fetchone()
    if int(count_row["c"] if count_row else 0) >= MAX_KB_DOCUMENTS:
        raise ValueError("ظرفیت پایگاه دانش به ۱۰ میلیون سند رسیده است.")
    doc_id = h[:16]
    now = int(time.time())
    conn.execute(
        "INSERT INTO kb_documents (id, title, source, lang, content_hash, bytes, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (doc_id, title, (source or "")[:300], (lang or "fa")[:8], h, len(content.encode("utf-8")), now, now),
    )
    for i, ch in enumerate(chunk_text(content)):
        conn.execute(
            "INSERT INTO kb_chunks (doc_id, chunk_index, content, token_approx) VALUES (?,?,?,?)",
            (doc_id, i, ch, max(1, len(ch) // 4)),
        )
    return {"ok": True, "duplicate": False, "id": doc_id, "title": title, "chunks": i + 1 if content else 0}


def search_chunks(conn, query: str, limit: int = 8) -> list[dict]:
    q = _norm(query)
    if not q:
        return []
    terms = [t for t in re.split(r"\s+", q) if len(t) > 1][:8]
    if not terms:
        return []
    # simple scored LIKE search (scalable step-1; vectors can replace later)
    rows = conn.execute(
        "SELECT c.content, c.doc_id, d.title, d.source FROM kb_chunks c JOIN kb_documents d ON d.id=c.doc_id"
    ).fetchall()
    scored = []
    for r in rows:
        body = _norm(r["content"])
        score = sum(3 if t in body else 0 for t in terms) + (2 if q in body else 0)
        if score > 0:
            scored.append({
                "score": score,
                "content": r["content"][:600],
                "doc_id": r["doc_id"],
                "title": r["title"],
                "source": r["source"] or "",
            })
    scored.sort(key=lambda x: -x["score"])
    return scored[:limit]


def list_documents(conn, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT id, title, source, lang, bytes, created_at FROM kb_documents ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def create_purchase(conn, user_key: str, plan_id: str, plan_name: str) -> dict:
    import secrets
    # prevent spam: one pending per user+plan
    row = conn.execute(
        "SELECT id FROM purchase_requests WHERE user_key=? AND plan_id=? AND status='pending'",
        (user_key, plan_id),
    ).fetchone()
    if row:
        return {"ok": True, "duplicate": True, "id": row["id"], "status": "pending"}
    pid = "PR-" + secrets.token_hex(4).upper()
    now = int(time.time())
    conn.execute(
        "INSERT INTO purchase_requests (id, user_key, plan_id, plan_name, status, created_at, updated_at) VALUES (?,?,?,?, 'pending', ?, ?)",
        (pid, user_key, plan_id, plan_name, now, now),
    )
    return {"ok": True, "duplicate": False, "id": pid, "status": "pending"}


def list_purchases(conn, user_key: str | None = None, staff: bool = False, limit: int = 50) -> list[dict]:
    if staff:
        rows = conn.execute(
            "SELECT * FROM purchase_requests ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM purchase_requests WHERE user_key=? ORDER BY created_at DESC LIMIT ?",
            (user_key or "guest", limit),
        ).fetchall()
    return [dict(r) for r in rows]


def update_purchase_status(conn, purchase_id: str, status: str, note: str = "") -> dict:
    status = (status or "").strip().lower()
    allowed = {"pending", "reviewing", "approved", "rejected", "cancelled"}
    if status not in allowed:
        raise ValueError("وضعیت نامعتبر است.")
    row = conn.execute("SELECT id FROM purchase_requests WHERE id=?", (purchase_id,)).fetchone()
    if not row:
        raise ValueError("درخواست پیدا نشد.")
    import time
    conn.execute(
        "UPDATE purchase_requests SET status=?, note=?, updated_at=? WHERE id=?",
        (status, (note or "")[:500], int(time.time()), purchase_id),
    )
    return {"ok": True, "id": purchase_id, "status": status}



def seed_builtin_knowledge(conn) -> int:
    """Load built-in corpus once when KB is empty. Returns number of new docs."""
    row = conn.execute("SELECT COUNT(*) AS c FROM kb_documents").fetchone()
    if row and int(row["c"] or 0) > 0:
        return 0
    try:
        from knowledge.seed_data import SEED_DOCUMENTS
    except Exception:
        return 0
    n = 0
    for doc in SEED_DOCUMENTS:
        try:
            r = ingest_document(
                conn,
                title=str(doc.get("title") or "سند"),
                content=str(doc.get("content") or ""),
                source=str(doc.get("source") or "کاوش/داخلی"),
                lang=str(doc.get("lang") or "fa"),
            )
            if r.get("ok") and not r.get("duplicate"):
                n += 1
        except Exception:
            continue
    return n


def answer_from_knowledge(conn, query: str, limit: int = 6) -> dict:
    """Build a user-facing answer from lexical KB hits (no external LLM)."""
    hits = search_chunks(conn, query, limit=limit)
    if not hits:
        # broad fallback: try individual tokens
        import re as _re
        tokens = [t for t in _re.split(r"\s+", (query or "").strip()) if len(t) > 2][:5]
        seen = set()
        for t in tokens:
            for h in search_chunks(conn, t, limit=3):
                key = (h.get("doc_id"), h.get("content", "")[:80])
                if key not in seen:
                    seen.add(key)
                    hits.append(h)
            if len(hits) >= limit:
                break
    if not hits:
        return {
            "ok": False,
            "answer": None,
            "hits": [],
        }
    lines = [
        "📚 پاسخ از موتور دانش کاوش (حالت جایگزین — بدون مدل ابری):",
        "",
    ]
    for i, h in enumerate(hits[:limit], 1):
        title = h.get("title") or "منبع"
        src = h.get("source") or ""
        body = (h.get("content") or "").strip()
        lines.append(f"{i}) {title}" + (f" — {src}" if src else ""))
        lines.append(body[:500])
        lines.append("")
    lines.append("اگر این پاسخ کامل نبود، سؤال را دقیق‌تر بپرسید یا وقتی سرویس AI در دسترس بود دوباره تلاش کنید.")
    return {"ok": True, "answer": "\n".join(lines).strip(), "hits": hits[:limit]}
