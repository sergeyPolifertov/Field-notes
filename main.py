from fastapi import FastAPI, HTTPException, Request, Cookie
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional
from database import (
    get_all_notes, get_notes_by_category, search_notes, get_all_categories,
    add_note, delete_note, update_note, get_note_by_id
)

app = FastAPI(title="Мой Блокнот")
templates = Jinja2Templates(directory="templates")

API_PASSWORD = "Trustno"


class Note(BaseModel):
    title: str
    content: str
    category: str = ""


class LoginRequest(BaseModel):
    password: str


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


@app.post("/logout")
def logout():
    return {"message": "Выход выполнен"}


@app.get("/categories")
def get_categories(request: Request, auth: Optional[str] = Cookie(None)):
    check_auth(auth)
    return get_all_categories()


@app.get("/notes")
def get_notes(request: Request, auth: Optional[str] = Cookie(None), q: str = "", category: str = ""):
    check_auth(auth)

    if q.strip():
        return search_notes(q.strip(), category)

    return get_notes_by_category(category)


@app.post("/notes")
def add_new_note(note: Note, request: Request, auth: Optional[str] = Cookie(None)):
    check_auth(auth)
    note_id = add_note(note.title, note.content, note.category)
    return {"message": "Заметка сохранена!", "id": note_id}


@app.delete("/notes/{note_id}")
def delete_existing_note(note_id: int, request: Request, auth: Optional[str] = Cookie(None)):
    check_auth(auth)
    if delete_note(note_id):
        return {"message": "Заметка удалена"}
    return {"message": "Заметка не найдена"}


@app.put("/notes/{note_id}")
def edit_note(note_id: int, note: Note, request: Request, auth: Optional[str] = Cookie(None)):
    check_auth(auth)
    if update_note(note_id, note.title, note.content, note.category):
        return {"message": "Заметка обновлена"}
    return {"message": "Заметка не найдена"}