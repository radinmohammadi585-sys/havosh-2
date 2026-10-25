"""Scalable knowledge store (SQLite now; designed for growth)."""
from __future__ import annotations
import hashlib
import json
import re
import time
from typing import Any

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
    if len(content) > 500_000:
        raise ValueError("حجم سند بیش از حد مجاز است.")
    h = content_hash(content)
    existing = conn.execute("SELECT id, title FROM kb_documents WHERE content_hash=?", (h,)).fetchone()
    if existing:
        return {"ok": True, "duplicate": True, "id": existing["id"], "title": existing["title"]}
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



def _norm_fa(query: str) -> str:
    q = (query or "").strip().lower()
    q = q.replace("ي", "ی").replace("ك", "ک").replace("ة", "ه")
    import re as _re
    q = _re.sub(r"[!?.؟،,؛:\"'«»()\[\]{}\u061f\uff1f]+", " ", q)
    q = _re.sub(r"\s+", " ", q).strip()
    return q


def _is_smalltalk(query: str) -> str | None:
    """Broad Persian/English greetings and chit-chat — never send these to KB search."""
    import re as _re
    core = _norm_fa(query)
    if not core:
        return None

    # exact and contains patterns
    greet_exact = {
        "سلام", "سلام علیکم", "سلام علیکم و رحمت الله", "درود", "درود بر شما",
        "هی", "هوی", "hello", "hi", "hey", "salam", "yo",
        "صبح بخیر", "ظهر بخیر", "عصر بخیر", "شب بخیر", "روز بخیر", "وقت بخیر",
    }
    if core in greet_exact or any(core == g or core.startswith(g + " ") for g in greet_exact):
        return (
            "سلام! من کاوش هستم 👋\n"
            "حالم خوبه و آماده‌ام کمکتان کنم.\n"
            "از درس، علوم، ریاضی، نجوم یا هر موضوعی بپرسید — یا بگویید براتان در وب جست‌وجو کنم."
        )

    how_patterns = [
        r"^خوبی\s*$", r"^خوبید\s*$", r"^خوب هستی", r"^حالت چطور", r"^حالت چطوره",
        r"^چطوری\s*$", r"^چطوره\s*$", r"^چطورید", r"^چه طور", r"^how are you",
        r"^what'?s up", r"^چه خبر", r"^اخوال", r"^احوال", r"^خوب هستین",
        r"^خوبی\s*\?", r"^خوبی\?",
    ]
    if any(_re.search(p, core) for p in how_patterns) or core in {
        "خوبی", "خوبید", "چطوری", "چطوره", "چه خبر", "حالت چطوره", "حالت چطوره؟",
    }:
        return (
            "ممنون، خوبم 🌟\n"
            "آماده‌ام برای درس، سؤال علمی، یا جست‌وجوی وب کمکتان کنم.\n"
            "چه کاری برایتان انجام بدهم؟"
        )

    thanks = {"ممنون", "ممنونم", "مرسی", "متشکرم", "تشکر", "خیلی ممنون", "دمت گرم", "thanks", "thank you", "thx"}
    if core in thanks or any(core.startswith(t) for t in ("ممنون", "مرسی", "تشکر", "thank")):
        return "خواهش می‌کنم 😊 اگر سؤال دیگری دارید بپرسید."

    byes = {"خداحافظ", "خدا حافظ", "فعلا", "فعلاً", "بدرود", "بای", "bye", "goodbye", "see you"}
    if core in byes or core.startswith("خداحافظ"):
        return "خداحافظ! موفق باشید 👋"

    ok_set = {"خوب", "عالی", "باشه", "باشه ممنون", "اوکی", "ok", "okay", "yes", "بله", "آره", "نه", "نخیر"}
    if core in ok_set:
        return "باشه. هر وقت سؤال داشتید بپرسید — می‌توانم از دانش کاوش یا وب کمک کنم."

    who = {"کی هستی", "تو کی هستی", "اسمت چیه", "who are you", "what are you"}
    if core in who or "کی هستی" in core or "who are you" in core:
        return (
            "من کاوش هستم؛ دستیار آموزشی مدرسه.\n"
            "می‌توانم از پایگاه دانش کاوش جواب بدهم و در صورت نیاز در وب جست‌وجو کنم."
        )

    return None


def answer_from_knowledge(conn, query: str, limit: int = 6) -> dict:
    """Relevant KB answers only; smalltalk never hits the corpus."""
    q = (query or "").strip()
    if not q:
        return {"ok": False, "answer": None, "hits": []}

    small = _is_smalltalk(q)
    if small:
        return {"ok": True, "answer": small, "hits": [], "provider": "smalltalk"}

    hits = search_chunks(conn, q, limit=max(limit, 8))
    min_score = 4  # stricter to avoid weak matches
    tokens = [t for t in __import__("re").split(r"\s+", _norm_fa(q)) if len(t) > 1]
    if len(tokens) >= 4:
        min_score = 3

    filtered = [h for h in (hits or []) if int(h.get("score") or 0) >= min_score]
    if not filtered:
        # Signal caller to try web search — do not invent irrelevant KB text
        return {
            "ok": False,
            "answer": None,
            "hits": [],
            "provider": "kavosh-knowledge-empty",
            "need_web": True,
        }

    top = filtered[:limit]
    lines = ["پاسخ بر اساس دانش کاوش (مرتبط با سؤال شما):", ""]
    for i, h in enumerate(top, 1):
        title = h.get("title") or "منبع"
        body = (h.get("content") or "").strip()
        if "تمرین پیشنهادی" in body:
            body = body.split("تمرین پیشنهادی")[0].strip()
        lines.append(f"{i}) {title}")
        lines.append(body[:450])
        lines.append("")
    return {"ok": True, "answer": "\n".join(lines).strip(), "hits": top, "provider": "kavosh-knowledge"}


