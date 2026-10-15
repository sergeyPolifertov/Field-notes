from fastapi import FastAPI, HTTPException, Request, Cookie, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
from werkzeug.security import generate_password_hash, check_password_hash
from database import (
    create_user, get_user_by_username, get_user_by_id, get_all_users,
    create_session, get_session, delete_session,
    get_all_notes_for_user, get_notes_by_category_for_user, search_notes_for_user, get_all_categories,
    add_note, delete_note, update_note, get_note_by_id, get_note_image,
    share_note_with_users, get_shared_users, set_note_public
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
    is_public: int = 0

class ShareRequest(BaseModel):
    user_ids: List[int] = []
    is_public: int = 0

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
    return templates.TemplateResponse(request=request, name="index.html")

# === Авторизация ===

@app.post("/register")
def register(req: RegisterRequest):
    if len(req.password) < 4:
        raise HTTPException(status_code=400, detail="Пароль должен быть не короче 4 символов")

    # Приводим имя к нижнему регистру
    username = req.username.lower().strip()

    if not username:
        raise HTTPException(status_code=400, detail="Имя пользователя не может быть пустым")

    password_hash = generate_password_hash(req.password)
    user_id = create_user(username, password_hash)
    if user_id is None:
        raise HTTPException(status_code=400, detail="Имя пользователя уже занято")

    session_id = create_session(user_id)
    return {"message": "Регистрация успешна", "session_id": session_id, "user_id": user_id, "username": username}

@app.post("/login")
def login(req: LoginRequest):
    username = req.username.lower().strip()
    user = get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=401, detail="Неверное имя пользователя или пароль")
    if not check_password_hash(user['password_hash'], req.password):
        raise HTTPException(status_code=401, detail="Неверное имя пользователя или пароль")
    session_id = create_session(user['id'])
    return {"message": "Вход выполнен", "session_id": session_id, "user_id": user['id'], "username": user['username']}

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
    return {"id": user['id'], "username": user['username']}

# === Пользователи ===

@app.get("/users")
def get_users_list(session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    users = get_all_users()
    return [u for u in users if u['id'] != user['id']]  # Исключаем себя

# === Загрузка файлов ===

@app.post("/upload")
def upload_image(file: UploadFile = File(...), session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Только изображения (jpg, png, gif, webp)")
    file_content = file.file.read()
    if len(file_content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Файл слишком большой (макс. 10 МБ)")
    ext = file.filename.split('.')[-1].lower()
    filename = f"{uuid.uuid4().hex}.jpg"
    filepath = os.path.join("uploads", filename)
    from PIL import Image
    import io
    try:
        img = Image.open(io.BytesIO(file_content))
        if img.mode in ('RGBA', 'P', 'LA'):
            img = img.convert('RGB')
        max_size = 1920
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        img.save(filepath, 'JPEG', quality=85, optimize=True)
    except Exception:
        with open(filepath, "wb") as f:
            f.write(file_content)
    return {"filename": filename, "url": f"/uploads/{filename}"}

# === Заметки ===

@app.get("/categories")
def get_categories(session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    return get_all_categories(user['id'])

@app.get("/notes")
def get_notes(session_id: Optional[str] = Cookie(None), q: str = "", category: str = ""):
    user = get_current_user(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    if q.strip():
        return search_notes_for_user(user['id'], q.strip(), category)
    return get_notes_by_category_for_user(user['id'], category)

@app.post("/notes")
def add_new_note(note: Note, session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    note_id = add_note(user['id'], note.title, note.content, note.category, note.image, note.is_public)
    return {"message": "Заметка сохранена!", "id": note_id}

@app.delete("/notes/{note_id}")
def delete_existing_note(note_id: int, session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    if delete_note(note_id, user['id']):
        return {"message": "Заметка удалена"}
    return {"message": "Заметка не найдена или нет доступа"}

@app.put("/notes/{note_id}")
def edit_note(note_id: int, note: Note, session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    conn = None
    try:
        from database import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT image FROM notes WHERE id = ? AND user_id = ?', (note_id, user['id']))
        old_row = cursor.fetchone()
        old_image = old_row['image'] if old_row else None
        if old_image and old_image != note.image:
            old_filepath = os.path.join("uploads", old_image)
            if os.path.exists(old_filepath):
                try:
                    os.remove(old_filepath)
                except Exception as e:
                    print(f"Не удалось удалить старое фото: {e}")
    finally:
        if conn:
            conn.close()
    if update_note(note_id, user['id'], note.title, note.content, note.category, note.image, note.is_public):
        return {"message": "Заметка обновлена"}
    return {"message": "Заметка не найдена или нет доступа"}

@app.delete("/notes/{note_id}/image")
def delete_note_image(note_id: int, session_id: Optional[str] = Cookie(None)):
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
        cursor.execute('SELECT title, content, category, is_public FROM notes WHERE id = ? AND user_id = ?', (note_id, user['id']))
        row = cursor.fetchone()
        if row:
            update_note(note_id, user['id'], row['title'], row['content'], row['category'], "", row['is_public'])
        conn.close()
        return {"message": "Картинка удалена"}
    return {"message": "Картинка не найдена"}

# === Общий доступ ===

@app.get("/notes/{note_id}/share")
def get_share_info(note_id: int, session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    note = get_note_by_id(note_id, user['id'])
    if not note:
        raise HTTPException(status_code=404, detail="Заметка не найдена")
    if note['user_id'] != user['id']:
        raise HTTPException(status_code=403, detail="Только владелец может управлять доступом")
    shared_users = get_shared_users(note_id, user['id'])
    return {"is_public": note['is_public'], "shared_with": shared_users}

@app.put("/notes/{note_id}/share")
def update_share(note_id: int, share_req: ShareRequest, session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    note = get_note_by_id(note_id, user['id'])
    if not note or note['user_id'] != user['id']:
        raise HTTPException(status_code=403, detail="Только владелец может управлять доступом")
    share_note_with_users(note_id, user['id'], share_req.user_ids)
    set_note_public(note_id, user['id'], share_req.is_public)
    return {"message": "Настройки доступа обновлены"}