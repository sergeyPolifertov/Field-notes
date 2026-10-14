import sqlite3
import os
from datetime import datetime, timedelta
import secrets

DB_NAME = "notebook.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Таблица заметок (добавляем user_id)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # Если таблица notes уже есть без user_id — добавляем поле
    try:
        cursor.execute('ALTER TABLE notes ADD COLUMN user_id INTEGER DEFAULT 1')
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Поле уже существует

    # Таблица сессий
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")


# === Пользователи ===

def create_user(username: str, password_hash: str):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO users (username, password_hash) VALUES (?, ?)',
            (username, password_hash)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None  # Имя уже занято
    finally:
        conn.close()


def get_user_by_username(username: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# === Сессии ===

def create_session(user_id: int, days=30):
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(days=days)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO sessions (id, user_id, expires_at) VALUES (?, ?, ?)',
        (session_id, user_id, expires_at.isoformat())
    )
    conn.commit()
    conn.close()
    return session_id


def get_session(session_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sessions WHERE id = ?', (session_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        session = dict(row)
        if datetime.fromisoformat(session['expires_at']) < datetime.now():
            delete_session(session_id)
            return None
        return session
    return None


def delete_session(session_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
    conn.commit()
    conn.close()


# === Заметки ===

def get_all_notes(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT * FROM notes WHERE user_id = ? ORDER BY created_at DESC',
        (user_id,)
    )
    notes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return notes


def get_notes_by_category(user_id: int, category: str):
    conn = get_connection()
    cursor = conn.cursor()
    if category:
        cursor.execute(
            'SELECT * FROM notes WHERE user_id = ? AND category = ? ORDER BY created_at DESC',
            (user_id, category)
        )
    else:
        cursor.execute(
            'SELECT * FROM notes WHERE user_id = ? ORDER BY created_at DESC',
            (user_id,)
        )
    notes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return notes


def search_notes(user_id: int, query: str, category: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    search_term = f"%{query.lower()}%"
    if category:
        cursor.execute(
            '''SELECT * FROM notes 
               WHERE user_id = ? AND (LOWER(title) LIKE ? OR LOWER(content) LIKE ?) 
               AND category = ?
               ORDER BY created_at DESC''',
            (user_id, search_term, search_term, category)
        )
    else:
        cursor.execute(
            '''SELECT * FROM notes 
               WHERE user_id = ? AND (LOWER(title) LIKE ? OR LOWER(content) LIKE ?)
               ORDER BY created_at DESC''',
            (user_id, search_term, search_term)
        )
    notes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return notes


def get_all_categories(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT DISTINCT category FROM notes WHERE user_id = ? AND category != "" ORDER BY category',
        (user_id,)
    )
    categories = [row['category'] for row in cursor.fetchall()]
    conn.close()
    return categories


def add_note(user_id: int, title: str, content: str, category: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO notes (user_id, title, content, category) VALUES (?, ?, ?, ?)',
        (user_id, title, content, category)
    )
    conn.commit()
    note_id = cursor.lastrowid
    conn.close()
    return note_id


def delete_note(note_id: int, user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM notes WHERE id = ? AND user_id = ?', (note_id, user_id))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted > 0


def update_note(note_id: int, user_id: int, title: str, content: str, category: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE notes SET title = ?, content = ?, category = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?',
        (title, content, category, note_id, user_id)
    )
    updated = cursor.rowcount
    conn.commit()
    conn.close()
    return updated > 0


init_db()