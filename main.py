from fastapi import FastAPI, HTTPException, Request, Cookie
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import json
import os
from typing import Optional

app = FastAPI(title="Мой Блокнот API")
templates = Jinja2Templates(directory="templates")

API_PASSWORD = "Trustno"


class Note(BaseModel):
    title: str
    content: str


class LoginRequest(BaseModel):
    password: str


NOTES_FILE = "notes.json"


def check_auth(password: Optional[str]):
    if password != API_PASSWORD:
        raise HTTPException(status_code=401, detail="Неверный пароль")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/login")
def login(login_req: LoginRequest):
    check_auth(login_req.password)
    return {"message": "Авторизация успешна"}


@app.get("/notes")
def get_notes(request: Request, auth: Optional[str] = Cookie(None)):
    check_auth(auth)
    if not os.path.exists(NOTES_FILE):
        return []
    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []


@app.post("/notes")
def add_note(note: Note, request: Request, auth: Optional[str] = Cookie(None)):
    check_auth(auth)
    notes = []
    if os.path.exists(NOTES_FILE):
        try:
            with open(NOTES_FILE, "r", encoding="utf-8") as f:
                notes = json.load(f)
        except json.JSONDecodeError:
            notes = []

    notes.append({"title": note.title, "content": note.content})

    with open(NOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=4)

    return {"message": "Заметка сохранена!"}


@app.delete("/notes/{note_id}")
def delete_note(note_id: int, request: Request, auth: Optional[str] = Cookie(None)):
    check_auth(auth)
    if not os.path.exists(NOTES_FILE):
        return {"message": "Заметка не найдена"}

    with open(NOTES_FILE, "r", encoding="utf-8") as f:
        notes = json.load(f)

    if 0 <= note_id < len(notes):
        deleted = notes.pop(note_id)
        with open(NOTES_FILE, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=4)
        return {"message": f"Заметка '{deleted['title']}' удалена"}

    return {"message": "Заметка не найдена"}