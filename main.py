import os
import uuid
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Cookie, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
from werkzeug.security import generate_password_hash, check_password_hash
from database import (
    create_user, get_user_by_username, get_user_by_email, get_user_by_id, get_all_users,
    create_session, get_session, delete_session,
    create_reset_token, get_user_by_reset_token, delete_reset_token, update_user_password,
    get_all_notes_for_user, get_notes_by_category_for_user, search_notes_for_user, get_all_categories,
    add_note, delete_note, update_note, get_note_by_id, get_note_image,
    share_note_with_users, get_shared_users, set_note_public
)

load_dotenv()

app = FastAPI(title="Семейный Блокнот")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# === Отправка почты ===
def send_email(to_email: str, subject: str, html_content: str):
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")

    if not all([smtp_server, smtp_user, smtp_pass]):
        print("⚠️ SMTP не настроен. Проверь файл .env")
        return False

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = smtp_user
    msg['To'] = to_email
    msg.attach(MIMEText(html_content, 'html'))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки почты: {e}")
        return False


# === Модели ===
class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class Note(BaseModel):
    title: str
    content: str
    category: str = ""
    image: str = ""
    is_public: int = 0


class ShareRequest(BaseModel):
    user_ids: List[int] = []
    is_public: int = 0


# === Вспомогательные ===
def get_current_user(session_id: Optional[str]):
    if not session_id: return None
    session = get_session(session_id)
    if not session: return None
    return get_user_by_id(session['user_id'])


# === Страницы ===
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


# === Авторизация ===
@app.post("/register")
def register(req: RegisterRequest):
    if len(req.password) < 4:
        raise HTTPException(status_code=400, detail="Пароль должен быть не короче 4 символов")

    username = req.username.lower().strip()
    email = req.email.lower().strip()

    if not username or not email:
        raise HTTPException(status_code=400, detail="Имя и почта обязательны")

    if get_user_by_username(username):
        raise HTTPException(status_code=400, detail="Имя пользователя уже занято")
    if get_user_by_email(email):
        raise HTTPException(status_code=400, detail="Эта почта уже зарегистрирована")

    password_hash = generate_password_hash(req.password)
    user_id = create_user(username, email, password_hash)
    if user_id is None:
        raise HTTPException(status_code=400, detail="Ошибка регистрации")

    # Отправляем приветственное письмо
    app_url = os.getenv("APP_URL", "http://localhost:8000")
    html = f"""
    <h2>Добро пожаловать в Семейный Блокнот! 📝</h2>
    <p>Привет, <b>{username}</b>!</p>
    <p>Ты успешно зарегистрировался. Твой логин для входа: <b>{username}</b></p>
    <p>Перейди в приложение: <a href="{app_url}">{app_url}</a></p>
    <p style="color: #888; font-size: 12px;">Если это был не ты, просто проигнорируй это письмо.</p>
    """
    send_email(email, "Регистрация в Семейном Блокноте", html)

    session_id = create_session(user_id)
    return {"message": "Регистрация успешна", "session_id": session_id, "user_id": user_id, "username": username}


@app.post("/login")
def login(req: LoginRequest):
    username = req.username.lower().strip()
    user = get_user_by_username(username)
    if not user or not check_password_hash(user['password_hash'], req.password):
        raise HTTPException(status_code=401, detail="Неверное имя пользователя или пароль")

    session_id = create_session(user['id'])
    return {"message": "Вход выполнен", "session_id": session_id, "user_id": user['id'], "username": user['username']}


@app.post("/logout")
def logout(session_id: Optional[str] = Cookie(None)):
    if session_id: delete_session(session_id)
    return {"message": "Выход выполнен"}


@app.get("/me")
def get_me(session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user: raise HTTPException(status_code=401, detail="Не авторизован")
    return {"id": user['id'], "username": user['username']}


# === Сброс пароля ===
@app.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest):
    email = req.email.lower().strip()
    user = get_user_by_email(email)

    # Всегда возвращаем успех, чтобы не раскрывать наличие почты в базе (безопасность)
    if user:
        token = create_reset_token(user['id'])
        app_url = os.getenv("APP_URL", "http://localhost:8000")
        reset_link = f"{app_url}/?reset={token}"

        html = f"""
        <h2>Сброс пароля 🔑</h2>
        <p>Привет! Ты (или кто-то другой) запросил сброс пароля для аккаунта <b>{user['username']}</b>.</p>
        <p>Нажми на кнопку ниже, чтобы установить новый пароль:</p>
        <p><a href="{reset_link}" style="background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Установить новый пароль</a></p>
        <p>Или скопируй ссылку: <a href="{reset_link}">{reset_link}</a></p>
        <p style="color: #888; font-size: 12px;">Ссылка действительна 1 час. Если это был не ты, проигнорируй письмо.</p>
        """
        send_email(email, "Сброс пароля - Семейный Блокнот", html)

    return {"message": "Если почта зарегистрирована, мы отправили инструкцию по сбросу."}


@app.post("/reset-password")
def reset_password(req: ResetPasswordRequest):
    if len(req.new_password) < 4:
        raise HTTPException(status_code=400, detail="Пароль должен быть не короче 4 символов")

    user = get_user_by_reset_token(req.token)
    if not user:
        raise HTTPException(status_code=400, detail="Неверная или просроченная ссылка")

    new_hash = generate_password_hash(req.new_password)
    update_user_password(user['id'], new_hash)
    delete_reset_token(req.token)  # Одноразовый токен

    return {"message": "Пароль успешно изменён!"}


# === Пользователи ===
@app.get("/users")
def get_users_list(session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user: raise HTTPException(status_code=401, detail="Не авторизован")
    return [u for u in get_all_users() if u['id'] != user['id']]


# === Загрузка файлов ===
@app.post("/upload")
def upload_image(file: UploadFile = File(...), session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user: raise HTTPException(status_code=401, detail="Не авторизован")

    allowed = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    if file.content_type not in allowed:
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
        if img.mode in ('RGBA', 'P', 'LA'): img = img.convert('RGB')
        max_size = 1920
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            img = img.resize((int(img.size[0] * ratio), int(img.size[1] * ratio)), Image.Resampling.LANCZOS)
        img.save(filepath, 'JPEG', quality=85, optimize=True)
    except Exception:
        with open(filepath, "wb") as f:
            f.write(file_content)

    return {"filename": filename, "url": f"/uploads/{filename}"}


# === Заметки ===
@app.get("/categories")
def get_categories(session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user: raise HTTPException(status_code=401, detail="Не авторизован")
    return get_all_categories(user['id'])


@app.get("/notes")
def get_notes(session_id: Optional[str] = Cookie(None), q: str = "", category: str = ""):
    user = get_current_user(session_id)
    if not user: raise HTTPException(status_code=401, detail="Не авторизован")
    if q.strip(): return search_notes_for_user(user['id'], q.strip(), category)
    return get_notes_by_category_for_user(user['id'], category)


@app.post("/notes")
def add_new_note(note: Note, session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user: raise HTTPException(status_code=401, detail="Не авторизован")
    note_id = add_note(user['id'], note.title, note.content, note.category, note.image, note.is_public)
    return {"message": "Заметка сохранена!", "id": note_id}


@app.delete("/notes/{note_id}")
def delete_existing_note(note_id: int, session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user: raise HTTPException(status_code=401, detail="Не авторизован")
    if delete_note(note_id, user['id']): return {"message": "Заметка удалена"}
    return {"message": "Заметка не найдена или нет доступа"}


@app.put("/notes/{note_id}")
def edit_note(note_id: int, note: Note, session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user: raise HTTPException(status_code=401, detail="Не авторизован")

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
        if conn: conn.close()

    if update_note(note_id, user['id'], note.title, note.content, note.category, note.image, note.is_public):
        return {"message": "Заметка обновлена"}
    return {"message": "Заметка не найдена или нет доступа"}


@app.delete("/notes/{note_id}/image")
def delete_note_image(note_id: int, session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user: raise HTTPException(status_code=401, detail="Не авторизован")
    image_path = get_note_image(note_id, user['id'])
    if image_path:
        filepath = os.path.join("uploads", image_path)
        if os.path.exists(filepath): os.remove(filepath)
        from database import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT title, content, category, is_public FROM notes WHERE id = ? AND user_id = ?',
                       (note_id, user['id']))
        row = cursor.fetchone()
        if row: update_note(note_id, user['id'], row['title'], row['content'], row['category'], "", row['is_public'])
        conn.close()
        return {"message": "Картинка удалена"}
    return {"message": "Картинка не найдена"}


@app.get("/notes/{note_id}/share")
def get_share_info(note_id: int, session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user: raise HTTPException(status_code=401, detail="Не авторизован")
    note = get_note_by_id(note_id, user['id'])
    if not note: raise HTTPException(status_code=404, detail="Заметка не найдена")
    if note['user_id'] != user['id']: raise HTTPException(status_code=403,
                                                          detail="Только владелец может управлять доступом")
    return {"is_public": note['is_public'], "shared_with": get_shared_users(note_id, user['id'])}


@app.put("/notes/{note_id}/share")
def update_share(note_id: int, share_req: ShareRequest, session_id: Optional[str] = Cookie(None)):
    user = get_current_user(session_id)
    if not user: raise HTTPException(status_code=401, detail="Не авторизован")
    note = get_note_by_id(note_id, user['id'])
    if not note or note['user_id'] != user['id']: raise HTTPException(status_code=403,
                                                                      detail="Только владелец может управлять доступом")
    share_note_with_users(note_id, user['id'], share_req.user_ids)
    set_note_public(note_id, user['id'], share_req.is_public)
    return {"message": "Настройки доступа обновлены"}