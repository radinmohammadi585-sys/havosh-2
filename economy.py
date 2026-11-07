
"""Economy, marketplace, bank, and online classes helpers (stdlib only)."""
from __future__ import annotations
import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Any


def _hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    dig = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"{salt}${dig.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, hx = stored.split("$", 1)
    except ValueError:
        return False
    dig = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return hmac.compare_digest(dig.hex(), hx)


def ensure_economy_tables(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS app_users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            role TEXT DEFAULT 'member',
            teacher_name TEXT,
            balance_kavosh REAL DEFAULT 0,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS market_listings (
            id TEXT PRIMARY KEY,
            seller_key TEXT NOT NULL,
            seller_name TEXT,
            title TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            currency TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS shop_items (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            currency TEXT DEFAULT 'kavosh',
            active INTEGER DEFAULT 1,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS stock_symbols (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            change_pct REAL DEFAULT 0,
            updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS banks (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            code TEXT,
            note TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS online_classes (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            teacher_key TEXT NOT NULL,
            teacher_name TEXT,
            description TEXT,
            schedule TEXT,
            status TEXT DEFAULT 'open',
            meet_url TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS class_grades (
            id TEXT PRIMARY KEY,
            class_id TEXT NOT NULL,
            student_key TEXT NOT NULL,
            student_label TEXT,
            score TEXT,
            note TEXT,
            teacher_key TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS teacher_messages (
            id TEXT PRIMARY KEY,
            class_id TEXT,
            from_key TEXT NOT NULL,
            to_key TEXT,
            body TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        """
    )
    # seed stocks if empty
    n = conn.execute("SELECT COUNT(*) AS c FROM stock_symbols").fetchone()["c"]
    if not n:
        now = int(time.time())
        seeds = [
            ("KAV", "کاوش‌تک", 1000.0, 1.2),
            ("EDU", "آموزش‌یار", 750.0, -0.5),
            ("STR", "ستاره‌پژوه", 1200.0, 2.1),
            ("SCI", "علم‌نوین", 890.0, 0.3),
        ]
        for i, name, price, ch in seeds:
            conn.execute(
                "INSERT INTO stock_symbols (id, name, price, change_pct, updated_at) VALUES (?,?,?,?,?)",
                (i, name, price, ch, now),
            )
    n2 = conn.execute("SELECT COUNT(*) AS c FROM shop_items").fetchone()["c"]
    if not n2:
        now = int(time.time())
        for title, price, desc in [
            ("بسته امتیاز چت", 5000, "امتیاز مجازی برای استفاده در مدرسه"),
            ("نشان کاوش", 2000, "نشان افتخاری پروفایل"),
            ("بلیت مسابقه", 1500, "ثبت‌نام یک مسابقه"),
        ]:
            conn.execute(
                "INSERT INTO shop_items (id, title, description, price, currency, active, created_at) VALUES (?,?,?,?,?,1,?)",
                ("SH-" + secrets.token_hex(3).upper(), title, desc, price, "kavosh", now),
            )


def register_user(conn, username: str, password: str) -> dict:
    username = re.sub(r"[^a-zA-Z0-9_\u0600-\u06FF]", "", (username or "").strip())[:32]
    if len(username) < 3:
        raise ValueError("نام کاربری حداقل ۳ کاراکتر باشد.")
    if len(password or "") < 6:
        raise ValueError("رمز عبور حداقل ۶ کاراکتر باشد.")
    if conn.execute("SELECT id FROM app_users WHERE username=?", (username,)).fetchone():
        raise ValueError("این نام کاربری قبلاً ثبت شده است.")
    uid = "U-" + secrets.token_hex(4).upper()
    conn.execute(
        "INSERT INTO app_users (id, username, password_hash, display_name, role, balance_kavosh, created_at) VALUES (?,?,?,?,?,?,?)",
        (uid, username, _hash_password(password), username, "member", 0, int(time.time())),
    )
    return {"ok": True, "id": uid, "username": username}


def login_user(conn, username: str, password: str) -> dict:
    username = (username or "").strip()
    row = conn.execute("SELECT * FROM app_users WHERE username=?", (username,)).fetchone()
    if not row or not _verify_password(password or "", row["password_hash"]):
        raise ValueError("نام کاربری یا رمز اشتباه است.")
    return dict(row)


def list_market(conn, limit: int = 50) -> list:
    rows = conn.execute(
        "SELECT * FROM market_listings WHERE status='active' ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_market_listing(conn, seller_key: str, seller_name: str, title: str, description: str, price: float, currency: str) -> dict:
    title = (title or "").strip()[:120]
    if not title:
        raise ValueError("عنوان لازم است.")
    currency = (currency or "kavosh").lower()
    if currency not in ("kavosh", "toman"):
        currency = "kavosh"
    try:
        price = float(price)
    except Exception:
        raise ValueError("قیمت نامعتبر است.")
    if price <= 0:
        raise ValueError("قیمت باید مثبت باشد.")
    lid = "M-" + secrets.token_hex(4).upper()
    conn.execute(
        "INSERT INTO market_listings (id, seller_key, seller_name, title, description, price, currency, status, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (lid, seller_key, (seller_name or seller_key)[:80], title, (description or "")[:2000], price, currency, "active", int(time.time())),
    )
    return {"ok": True, "id": lid}


def list_shop(conn) -> list:
    rows = conn.execute("SELECT * FROM shop_items WHERE active=1 ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def list_stocks(conn) -> list:
    rows = conn.execute("SELECT * FROM stock_symbols ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def tick_stocks(conn) -> None:
    """Small simulated price drift."""
    import random
    now = int(time.time())
    for r in conn.execute("SELECT id, price FROM stock_symbols").fetchall():
        delta = random.uniform(-1.5, 1.5)
        new_p = max(10.0, float(r["price"]) * (1 + delta / 100))
        conn.execute(
            "UPDATE stock_symbols SET price=?, change_pct=?, updated_at=? WHERE id=?",
            (round(new_p, 2), round(delta, 2), now, r["id"]),
        )


def list_banks(conn) -> list:
    return [dict(r) for r in conn.execute("SELECT * FROM banks ORDER BY created_at DESC").fetchall()]


def add_bank(conn, name: str, code: str = "", note: str = "") -> dict:
    name = (name or "").strip()[:100]
    if not name:
        raise ValueError("نام بانک لازم است.")
    bid = "B-" + secrets.token_hex(3).upper()
    conn.execute(
        "INSERT INTO banks (id, name, code, note, created_at) VALUES (?,?,?,?,?)",
        (bid, name, (code or "")[:40], (note or "")[:500], int(time.time())),
    )
    return {"ok": True, "id": bid}


def list_classes(conn) -> list:
    return [dict(r) for r in conn.execute("SELECT * FROM online_classes ORDER BY created_at DESC LIMIT 100").fetchall()]


def create_class(conn, teacher_key: str, teacher_name: str, title: str, description: str, schedule: str, meet_url: str = "") -> dict:
    title = (title or "").strip()[:120]
    if not title:
        raise ValueError("عنوان کلاس لازم است.")
    cid = "CL-" + secrets.token_hex(4).upper()
    meet = (meet_url or "").strip()[:500]
    if not meet:
        meet = f"https://meet.jit.si/Kavosh-{cid}"
    conn.execute(
        "INSERT INTO online_classes (id, title, teacher_key, teacher_name, description, schedule, status, meet_url, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (cid, title, teacher_key, (teacher_name or "")[:80], (description or "")[:2000], (schedule or "")[:200], "open", meet, int(time.time())),
    )
    return {"ok": True, "id": cid, "meet_url": meet}


def add_grade(conn, class_id: str, student_key: str, student_label: str, score: str, note: str, teacher_key: str) -> dict:
    gid = "G-" + secrets.token_hex(4).upper()
    conn.execute(
        "INSERT INTO class_grades (id, class_id, student_key, student_label, score, note, teacher_key, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (gid, class_id, student_key[:80], (student_label or "")[:80], (score or "")[:40], (note or "")[:500], teacher_key, int(time.time())),
    )
    return {"ok": True, "id": gid}


def list_grades(conn, class_id: str | None = None) -> list:
    if class_id:
        rows = conn.execute("SELECT * FROM class_grades WHERE class_id=? ORDER BY created_at DESC", (class_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM class_grades ORDER BY created_at DESC LIMIT 100").fetchall()
    return [dict(r) for r in rows]


def add_teacher_message(conn, from_key: str, body: str, class_id: str = "", to_key: str = "") -> dict:
    body = (body or "").strip()[:2000]
    if not body:
        raise ValueError("متن پیام خالی است.")
    mid = "TM-" + secrets.token_hex(4).upper()
    conn.execute(
        "INSERT INTO teacher_messages (id, class_id, from_key, to_key, body, created_at) VALUES (?,?,?,?,?,?)",
        (mid, class_id or None, from_key, to_key or None, body, int(time.time())),
    )
    return {"ok": True, "id": mid}


def list_teacher_messages(conn, limit: int = 50) -> list:
    rows = conn.execute("SELECT * FROM teacher_messages ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def set_teacher_name(conn, username: str, teacher_name: str) -> dict:
    teacher_name = (teacher_name or "").strip()[:80]
    if len(teacher_name) < 2:
        raise ValueError("نام نمایشی معلم لازم است.")
    conn.execute("UPDATE app_users SET teacher_name=?, display_name=? WHERE username=?", (teacher_name, teacher_name, username))
    return {"ok": True, "teacher_name": teacher_name}
