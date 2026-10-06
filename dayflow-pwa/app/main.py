from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="DayFlow", version="0.1.0")
db.init_db()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

Due = Literal["overdue", "today", "tomorrow", "week", "later", "none"]
Area = Literal["Работа", "Личное"]
Priority = Literal["urgent-important", "important", "urgent", "low"]


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    due: Due = "none"
    in_now: bool = False
    area: Area = "Работа"
    project: str = Field(default="", max_length=120)
    priority: Priority = "important"
    done: bool = False


class TaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    due: Due | None = None
    in_now: bool | None = None
    area: Area | None = None
    project: str | None = Field(default=None, max_length=120)
    priority: Priority | None = None
    done: bool | None = None


class PhraseIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


def parse_phrase(text: str) -> dict:
    raw = text.strip()
    lower = raw.lower()

    if "послезавтра" in lower:
        due = "week"
    elif "завтра" in lower:
        due = "tomorrow"
    elif re.search(r"на этой неделе|на неделе|до конца недели", lower):
        due = "week"
    elif re.search(r"потом|когда-нибудь|как-нибудь|не горит", lower):
        due = "later"
    else:
        due = "today"

    area = "Работа"
    if re.search(r"домой|\bдом\b|продукт|магазин|личн|трениров|врач|квартир|родител|семь", lower):
        area = "Личное"
    if re.search(r"клиент|битрикс|сервер|\bкп\b|коммерческ|проект|сч[её]т|работ|стоматолог", lower):
        area = "Работа"

    priority = "important"
    if re.search(r"срочно.{0,20}важ|важ.{0,20}срочно", lower):
        priority = "urgent-important"
    elif re.search(r"срочно|горит|как можно скорее", lower):
        priority = "urgent"
    elif re.search(r"когда-нибудь|если будет время|неважно|не важно", lower):
        priority = "low"

    name = raw
    name = re.sub(
        r"\b(сегодня|завтра|послезавтра|на этой неделе|на неделе|до конца недели|потом|когда-нибудь|как-нибудь)\b",
        " ",
        name,
        flags=re.I,
    )
    name = re.sub(r"\b(срочно и важно|важно и срочно|срочно|важно|обязательно)\b", " ", name, flags=re.I)
    name = re.sub(r"\s+", " ", name).strip(" -,.:;") or raw

    project = ""
    match = re.search(r"\bпо\s+([А-Яа-яA-Za-z0-9Ёё._\- ]{3,60})$", raw, flags=re.I)
    if match:
        possible = match.group(1).strip()
        if possible.lower() not in {"этому", "этому вопросу", "этому делу"}:
            project = possible

    return {
        "name": name,
        "due": due,
        "in_now": False,
        "area": area,
        "project": project,
        "priority": priority,
        "done": False,
        "source_text": raw,
    }


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/manifest.json")
def manifest():
    return FileResponse(STATIC_DIR / "manifest.json", media_type="application/manifest+json")


@app.get("/service-worker.js")
def service_worker():
    return FileResponse(STATIC_DIR / "service-worker.js", media_type="application/javascript")


@app.get("/api/tasks")
def api_tasks():
    return db.list_tasks()


@app.post("/api/tasks", status_code=201)
def api_create_task(payload: TaskCreate):
    if payload.in_now:
        now_count = sum(1 for t in db.list_tasks() if t["in_now"] and not t["done"])
        if now_count >= 3:
            raise HTTPException(409, "В «Сейчас» уже 3 задачи")
    return db.create_task(payload.model_dump())


@app.patch("/api/tasks/{task_id}")
def api_update_task(task_id: int, payload: TaskUpdate):
    data = payload.model_dump(exclude_none=True)
    if data.get("in_now"):
        now_count = sum(1 for t in db.list_tasks() if t["in_now"] and not t["done"] and t["id"] != task_id)
        if now_count >= 3:
            raise HTTPException(409, "В «Сейчас» уже 3 задачи")
    if data.get("done"):
        data["in_now"] = False
    task = db.update_task(task_id, data)
    if not task:
        raise HTTPException(404, "Задача не найдена")
    return task


@app.delete("/api/tasks/{task_id}", status_code=204)
def api_delete_task(task_id: int):
    if not db.delete_task(task_id):
        raise HTTPException(404, "Задача не найдена")


@app.post("/api/parse")
def api_parse(payload: PhraseIn):
    return parse_phrase(payload.text)


@app.post("/api/voice-task", status_code=201)
def api_voice_task(payload: PhraseIn):
    parsed = parse_phrase(payload.text)
    return db.create_task(parsed)


@app.post("/api/transcribe")
async def api_transcribe(audio: UploadFile = File(...)):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            503,
            "На сервере не задан OPENAI_API_KEY. Используйте браузерное распознавание или настройте ключ.",
        )

    raw = await audio.read()
    if not raw:
        raise HTTPException(400, "Пустая аудиозапись")
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(413, "Аудиозапись слишком большая")

    model = os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")
    mime = audio.content_type or "audio/webm"
    filename = audio.filename or "voice.webm"

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": model, "language": "ru"},
                files={"file": (filename, raw, mime)},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Ошибка сервиса распознавания: {exc}") from exc

    if response.status_code >= 400:
        try:
            detail = response.json()
        except json.JSONDecodeError:
            detail = response.text
        raise HTTPException(502, f"Не удалось распознать речь: {detail}")

    payload = response.json()
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(422, "Речь не распознана")
    return {"text": text}
