import sqlite3
from datetime import datetime
from config import DB_PATH


def _connect():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id   INTEGER UNIQUE NOT NULL,
                first_name    TEXT NOT NULL,
                last_name     TEXT NOT NULL,
                email         TEXT NOT NULL,
                phone         TEXT NOT NULL,
                registered_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL REFERENCES users(id),
                reminder_key  TEXT NOT NULL,
                sent_at       TEXT NOT NULL,
                UNIQUE(user_id, reminder_key)
            )
        """)


def add_user(telegram_id: int, first_name: str, last_name: str,
             email: str, phone: str) -> int:
    """Добавляет пользователя. Возвращает его id."""
    registered_at = datetime.utcnow().isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO users (telegram_id, first_name, last_name, email, phone, registered_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (telegram_id, first_name, last_name, email, phone, registered_at),
        )
        return cur.lastrowid


def get_user_by_telegram_id(telegram_id: int) -> dict | None:
    """Возвращает пользователя по telegram_id или None."""
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return dict(row) if row else None


def get_all_users() -> list[dict]:
    """Возвращает всех зарегистрированных пользователей."""
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM users").fetchall()
        return [dict(r) for r in rows]


def is_reminder_sent(user_id: int, reminder_key: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM reminders_log WHERE user_id = ? AND reminder_key = ?",
            (user_id, reminder_key),
        ).fetchone()
        return row is not None


def mark_reminder_sent(user_id: int, reminder_key: str):
    sent_at = datetime.utcnow().isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO reminders_log (user_id, reminder_key, sent_at)
            VALUES (?, ?, ?)
            """,
            (user_id, reminder_key, sent_at),
        )
