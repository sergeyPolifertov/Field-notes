from fastapi import FastAPI, HTTPException, Request, Cookie, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from werkzeug.security import generate_password_hash, check_password_hash
from database import (
    create_user, get_user_by_username, get_user_by_id,
    create_session, get_session, delete_session,
    get_all_notes, get_notes_by_category, search_notes, get_all_categories,
    add_note, delete_note, update_note, get_note_image
)
import os
import uuid

app = FastAPI(title="Семейный Блокнот")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# === Модели ===

class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


class Note(BaseModel):
    title: str
    content: str
    category: str = ""
    image: str = ""


# === Вспомогательные функции ===

def get_current_user(session_id: Optional[str]):
    if not session_id:
        return None
    session = get_session(session_id)
    if not session:
        return None
    return get_user_by_id(session['user_id'])


# === Страницы ===

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"request": request, "user": user}
    )


# === Авторизация ===

@app.post("/register")
def register(req: RegisterRequest):
    if len(req.password) < 4:
        raise HTTPException(status_code=400, detail="Пароль должен быть не короче 4 символов")

    password_hash = generate_password_hash(req.password)
    user_id = create_user(req.username, password_hash)
    if user_id is None:
        raise HTTPException(status_code=400, detail="Имя пользователя уже занято")

    session_id = create_session(user_id)
    return {"message": "Регистрация успешна", "session_id": session_id}


@app.post("/login")
def login(req: LoginRequest):
    user = get_user_by_username(req.username)
    if not user:
        raise HTTPException(status_code=401, detail="Неверное имя пользователя или пароль")

    if not check_password_hash(user['password_hash'], req.password):
        raise HTTPException(status_code=401, detail="Неверное имя пользователя или пароль")

    session_id = create_session(user['id'])
    return {"message": "Вход выполнен", "session_id": session_id}


@app.post("/logout")
def logout(session_id: Optional[str] = Cookie(None)):
    if session_id:
        delete_session(session_id)
    return {"message": "Выход выполнен"}


@app.get("/me")
def get_me(session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    return {"username": user['username']}


# === Загрузка файлов ===

@app.post("/upload")
@app.post("/upload")
def upload_image(file: UploadFile = File(...), session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")

    allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Только изображения (jpg, png, gif, webp)")

    file_content = file.file.read()
    if len(file_content) > 10 * 1024 * 1024:  # Увеличили лимит до 10 МБ (до сжатия)
        raise HTTPException(status_code=400, detail="Файл слишком большой (макс. 10 МБ)")

    # Генерируем уникальное имя файла
    ext = file.filename.split('.')[-1].lower()
    filename = f"{uuid.uuid4().hex}.jpg"  # Всегда сохраняем как JPG для сжатия
    filepath = os.path.join("uploads", filename)

    # Сжимаем картинку через Pillow
    from PIL import Image
    import io

    try:
        img = Image.open(io.BytesIO(file_content))

        # Конвертируем в RGB (если PNG с прозрачностью или RGBA)
        if img.mode in ('RGBA', 'P', 'LA'):
            img = img.convert('RGB')

        # Ресайз: если длинная сторона больше 1920px — уменьшаем
        max_size = 1920
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        # Сохраняем с качеством 85% (оптимальный баланс качество/размер)
        img.save(filepath, 'JPEG', quality=85, optimize=True)

    except Exception as e:
        # Если не удалось сжать — сохраняем оригинал
        with open(filepath, "wb") as f:
            f.write(file_content)

    return {"filename": filename, "url": f"/uploads/{filename}"}

# === Заметки ===

@app.get("/categories")
def get_categories(request: Request, session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    return get_all_categories(user['id'])


@app.get("/notes")
def get_notes(request: Request, session_id: Optional[str] = Cookie(None), q: str = "", category: str = ""):
    user = get_current_user(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")

    if q.strip():
        return search_notes(user['id'], q.strip(), category)

    return get_notes_by_category(user['id'], category)


@app.post("/notes")
def add_new_note(note: Note, request: Request, session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    note_id = add_note(user['id'], note.title, note.content, note.category, note.image)
    return {"message": "Заметка сохранена!", "id": note_id}


@app.delete("/notes/{note_id}")
def delete_existing_note(note_id: int, request: Request, session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    if delete_note(note_id, user['id']):
        return {"message": "Заметка удалена"}
    return {"message": "Заметка не найдена"}


@app.put("/notes/{note_id}")
def edit_note(note_id: int, note: Note, request: Request, session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    if update_note(note_id, user['id'], note.title, note.content, note.category, note.image):
        return {"message": "Заметка обновлена"}
    return {"message": "Заметка не найдена"}


@app.delete("/notes/{note_id}/image")
def delete_note_image(note_id: int, request: Request, session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")

    image_path = get_note_image(note_id, user['id'])
    if image_path:
        filepath = os.path.join("uploads", image_path)
        if os.path.exists(filepath):
            os.remove(filepath)

        from database import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT title, content, category FROM notes WHERE id = ? AND user_id = ?', (note_id, user['id']))
        row = cursor.fetchone()
        if row:
            update_note(note_id, user['id'], row['title'], row['content'], row['category'], "")
        conn.close()
        return {"message": "Картинка удалена"}
    return {"message": "Картинка не найдена"}