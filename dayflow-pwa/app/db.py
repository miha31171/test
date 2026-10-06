from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "dayflow.db"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                due TEXT NOT NULL DEFAULT 'none',
                in_now INTEGER NOT NULL DEFAULT 0,
                area TEXT NOT NULL DEFAULT 'Работа',
                project TEXT NOT NULL DEFAULT '',
                priority TEXT NOT NULL DEFAULT 'important',
                done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        if count == 0:
            rows = [
                ("Позвонить Иванову по настройке Bitrix24", "today", 1, "Работа", "Клиент Иванов", "urgent-important", 0),
                ("Отправить коммерческое предложение", "today", 1, "Работа", "Новый клиент", "urgent-important", 0),
                ("Оплатить сервер", "today", 0, "Работа", "Инфраструктура", "important", 0),
                ("Купить продукты домой", "today", 0, "Личное", "Дом", "urgent", 0),
                ("Подготовить следующий этап приложения", "tomorrow", 0, "Работа", "Задачник", "important", 0),
                ("Посмотреть варианты ноутбука", "week", 0, "Личное", "Покупки", "low", 0),
            ]
            conn.executemany(
                "INSERT INTO tasks(name,due,in_now,area,project,priority,done) VALUES(?,?,?,?,?,?,?)",
                rows,
            )


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "due": row["due"],
        "in_now": bool(row["in_now"]),
        "area": row["area"],
        "project": row["project"],
        "priority": row["priority"],
        "done": bool(row["done"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_tasks() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM tasks ORDER BY done, in_now DESC, id DESC").fetchall()
    return [row_to_dict(r) for r in rows]


def get_task(task_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    return row_to_dict(row) if row else None


def create_task(data: dict[str, Any]) -> dict[str, Any]:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO tasks(name,due,in_now,area,project,priority,done)
               VALUES(?,?,?,?,?,?,?)""",
            (
                data["name"].strip(),
                data.get("due", "none"),
                1 if data.get("in_now") else 0,
                data.get("area", "Работа"),
                data.get("project", "").strip(),
                data.get("priority", "important"),
                1 if data.get("done") else 0,
            ),
        )
        task_id = cur.lastrowid
    return get_task(task_id)  # type: ignore[return-value]


def update_task(task_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {"name", "due", "in_now", "area", "project", "priority", "done"}
    fields = []
    values: list[Any] = []
    for key, value in data.items():
        if key not in allowed:
            continue
        fields.append(f"{key}=?")
        if key in {"in_now", "done"}:
            value = 1 if value else 0
        if key in {"name", "project"} and isinstance(value, str):
            value = value.strip()
        values.append(value)
    if not fields:
        return get_task(task_id)
    fields.append("updated_at=CURRENT_TIMESTAMP")
    values.append(task_id)
    with connect() as conn:
        cur = conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id=?", values)
        if cur.rowcount == 0:
            return None
    return get_task(task_id)


def delete_task(task_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    return cur.rowcount > 0
