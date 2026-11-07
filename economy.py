
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
            join_code TEXT,
            class_type TEXT,
            book_id TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS class_packages (
            user_key TEXT PRIMARY KEY,
            rooms_total INTEGER NOT NULL,
            rooms_used INTEGER NOT NULL DEFAULT 0,
            source TEXT,
            updated_at INTEGER NOT NULL
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

    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(online_classes)").fetchall()]
        for col, typ in [("join_code", "TEXT"), ("class_type", "TEXT"), ("book_id", "TEXT"), ("meet_url", "TEXT")]:
            if col not in cols:
                conn.execute(f"ALTER TABLE online_classes ADD COLUMN {col} {typ}")
    except Exception:
        pass

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


def create_class(conn, teacher_key: str, teacher_name: str, title: str, description: str, schedule: str, meet_url: str = "", class_type: str = "", book_id: str = "", is_staff: bool = False) -> dict:
    title = (title or "").strip()[:120]
    if not title:
        raise ValueError("عنوان کلاس لازم است.")
    ensure_package(conn, teacher_key, is_staff=is_staff)
    row = conn.execute("SELECT rooms_total, rooms_used FROM class_packages WHERE user_key=?", (teacher_key,)).fetchone()
    if row and int(row["rooms_used"]) >= int(row["rooms_total"]):
        raise ValueError("سقف ساخت اتاق پر شده. پکیج ۵۰ اتاقه تهیه کنید.")
    cid = "CL-" + secrets.token_hex(4).upper()
    join_code = secrets.token_hex(3).upper()
    meet = (meet_url or "").strip()[:500] or f"https://meet.jit.si/Kavosh-{cid}"
    conn.execute(
        "INSERT INTO online_classes (id, title, teacher_key, teacher_name, description, schedule, status, meet_url, join_code, class_type, book_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (cid, title, teacher_key, (teacher_name or "")[:80], (description or "")[:2000], (schedule or "")[:200], "open", meet, join_code, (class_type or "")[:80], (book_id or "")[:80], int(time.time())),
    )
    conn.execute(
        "UPDATE class_packages SET rooms_used = rooms_used + 1, updated_at=? WHERE user_key=?",
        (int(time.time()), teacher_key),
    )
    return {"ok": True, "id": cid, "meet_url": meet, "join_code": join_code}


def ensure_package(conn, user_key: str, is_staff: bool = False) -> dict:
    row = conn.execute("SELECT * FROM class_packages WHERE user_key=?", (user_key,)).fetchone()
    now = int(time.time())
    if is_staff:
        if not row:
            conn.execute(
                "INSERT INTO class_packages (user_key, rooms_total, rooms_used, source, updated_at) VALUES (?,?,?,?,?)",
                (user_key, 50, 0, "staff-auto", now),
            )
            return {"rooms_total": 50, "rooms_used": 0}
        if int(row["rooms_total"]) < 50:
            conn.execute(
                "UPDATE class_packages SET rooms_total=50, source=?, updated_at=? WHERE user_key=?",
                ("staff-auto", now, user_key),
            )
        return {"rooms_total": max(50, int(row["rooms_total"])), "rooms_used": int(row["rooms_used"])}
    if not row:
        conn.execute(
            "INSERT INTO class_packages (user_key, rooms_total, rooms_used, source, updated_at) VALUES (?,?,?,?,?)",
            (user_key, 0, 0, "none", now),
        )
        return {"rooms_total": 0, "rooms_used": 0}
    return {"rooms_total": int(row["rooms_total"]), "rooms_used": int(row["rooms_used"])}


def buy_class_package(conn, user_key: str) -> dict:
    now = int(time.time())
    row = conn.execute("SELECT * FROM class_packages WHERE user_key=?", (user_key,)).fetchone()
    if row:
        conn.execute(
            "UPDATE class_packages SET rooms_total = rooms_total + 50, source=?, updated_at=? WHERE user_key=?",
            ("purchase", now, user_key),
        )
    else:
        conn.execute(
            "INSERT INTO class_packages (user_key, rooms_total, rooms_used, source, updated_at) VALUES (?,?,?,?,?)",
            (user_key, 50, 0, "purchase", now),
        )
    row = conn.execute("SELECT * FROM class_packages WHERE user_key=?", (user_key,)).fetchone()
    return {
        "ok": True,
        "rooms_total": int(row["rooms_total"]),
        "rooms_used": int(row["rooms_used"]),
        "price_kavosh": 399000,
        "price_toman": 3990000,
        "message": "پکیج ۵۰ اتاقه ثبت شد.",
    }


def get_package(conn, user_key: str) -> dict:
    row = conn.execute("SELECT * FROM class_packages WHERE user_key=?", (user_key,)).fetchone()
    if not row:
        return {"rooms_total": 0, "rooms_used": 0, "source": "none"}
    return {"rooms_total": int(row["rooms_total"]), "rooms_used": int(row["rooms_used"]), "source": row["source"] or ""}


def find_class_by_code(conn, code: str):
    code = (code or "").strip().upper()
    if not code:
        return None
    row = conn.execute("SELECT * FROM online_classes WHERE upper(join_code)=? AND status='open'", (code,)).fetchone()
    return dict(row) if row else None


GRADE_BOOKS = [
    # سال تحصیلی ۱۴۰۵–۱۴۰۶ — عناوین رسمی پایگاه کتاب‌های درسی (chap.sch.ir)
    # پایه دوم
    {"id": "201", "grade": 2, "code": "201", "year": "1405-1406", "title": "آموزش قرآن (دوم)"},
    {"id": "202", "grade": 2, "code": "202", "year": "1405-1406", "title": "هدیه‌های آسمان (دوم)"},
    {"id": "203", "grade": 2, "code": "203", "year": "1405-1406", "title": "فارسی (دوم)"},
    {"id": "204", "grade": 2, "code": "204", "year": "1405-1406", "title": "نگارش فارسی (دوم)"},
    {"id": "205", "grade": 2, "code": "205", "year": "1405-1406", "title": "ریاضی (دوم)"},
    {"id": "206", "grade": 2, "code": "206", "year": "1405-1406", "title": "علوم تجربی (دوم)"},
    # پایه سوم
    {"id": "301", "grade": 3, "code": "301", "year": "1405-1406", "title": "آموزش قرآن (سوم)"},
    {"id": "302", "grade": 3, "code": "302", "year": "1405-1406", "title": "هدیه‌های آسمان (سوم)"},
    {"id": "303", "grade": 3, "code": "303", "year": "1405-1406", "title": "فارسی (سوم)"},
    {"id": "304", "grade": 3, "code": "304", "year": "1405-1406", "title": "نگارش فارسی (سوم)"},
    {"id": "305", "grade": 3, "code": "305", "year": "1405-1406", "title": "ریاضی (سوم)"},
    {"id": "306", "grade": 3, "code": "306", "year": "1405-1406", "title": "علوم تجربی (سوم)"},
    {"id": "307", "grade": 3, "code": "307", "year": "1405-1406", "title": "مطالعات اجتماعی (سوم)"},
    # پایه چهارم
    {"id": "401", "grade": 4, "code": "401", "year": "1405-1406", "title": "آموزش قرآن (چهارم)"},
    {"id": "402", "grade": 4, "code": "402", "year": "1405-1406", "title": "هدیه‌های آسمان (چهارم)"},
    {"id": "403", "grade": 4, "code": "403", "year": "1405-1406", "title": "فارسی (چهارم)"},
    {"id": "404", "grade": 4, "code": "404", "year": "1405-1406", "title": "نگارش فارسی (چهارم)"},
    {"id": "405", "grade": 4, "code": "405", "year": "1405-1406", "title": "ریاضی (چهارم)"},
    {"id": "406", "grade": 4, "code": "406", "year": "1405-1406", "title": "علوم تجربی (چهارم)"},
    {"id": "407", "grade": 4, "code": "407", "year": "1405-1406", "title": "مطالعات اجتماعی (چهارم)"},
    {"id": "408", "grade": 4, "code": "408", "year": "1405-1406", "title": "کتاب کار آموزش خط تحریری (چهارم)"},
    # پایه پنجم
    {"id": "501", "grade": 5, "code": "501", "year": "1405-1406", "title": "آموزش قرآن (پنجم)"},
    {"id": "502", "grade": 5, "code": "502", "year": "1405-1406", "title": "هدیه‌های آسمان (پنجم)"},
    {"id": "503", "grade": 5, "code": "503", "year": "1405-1406", "title": "فارسی (پنجم)"},
    {"id": "504", "grade": 5, "code": "504", "year": "1405-1406", "title": "نگارش فارسی (پنجم)"},
    {"id": "505", "grade": 5, "code": "505", "year": "1405-1406", "title": "ریاضی (پنجم)"},
    {"id": "506", "grade": 5, "code": "506", "year": "1405-1406", "title": "علوم تجربی (پنجم)"},
    {"id": "507", "grade": 5, "code": "507", "year": "1405-1406", "title": "مطالعات اجتماعی (پنجم)"},
    {"id": "508", "grade": 5, "code": "508", "year": "1405-1406", "title": "کتاب کار آموزش خط تحریری (پنجم)"},
    # پایه ششم
    {"id": "601", "grade": 6, "code": "601", "year": "1405-1406", "title": "آموزش قرآن (ششم)"},
    {"id": "602", "grade": 6, "code": "602", "year": "1405-1406", "title": "هدیه‌های آسمان (ششم)"},
    {"id": "603", "grade": 6, "code": "603", "year": "1405-1406", "title": "فارسی (ششم)"},
    {"id": "604", "grade": 6, "code": "604", "year": "1405-1406", "title": "نگارش فارسی (ششم)"},
    {"id": "605", "grade": 6, "code": "605", "year": "1405-1406", "title": "ریاضی (ششم)"},
    {"id": "606", "grade": 6, "code": "606", "year": "1405-1406", "title": "علوم تجربی (ششم)"},
    {"id": "607", "grade": 6, "code": "607", "year": "1405-1406", "title": "مطالعات اجتماعی (ششم)"},
    {"id": "608", "grade": 6, "code": "608", "year": "1405-1406", "title": "کتاب کار آموزش خط تحریری (ششم)"},
    {"id": "612", "grade": 6, "code": "612", "year": "1405-1406", "title": "تفکر و پژوهش (ششم)"},
    {"id": "617", "grade": 6, "code": "617", "year": "1405-1406", "title": "کار و فناوری (ششم)"},
]


def list_books():
    return list(GRADE_BOOKS)


def book_by_id(book_id: str):
    for b in GRADE_BOOKS:
        if b["id"] == book_id or b.get("code") == book_id:
            return b
    return None


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
