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

    # Таблица заметок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT DEFAULT '',
            image TEXT DEFAULT '',
            is_public INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # Добавляем поле is_public если его нет
    try:
        cursor.execute('ALTER TABLE notes ADD COLUMN is_public INTEGER DEFAULT 0')
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute('ALTER TABLE notes ADD COLUMN image TEXT DEFAULT ""')
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute('ALTER TABLE notes ADD COLUMN user_id INTEGER DEFAULT 1')
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Таблица общего доступа
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shared_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            note_id INTEGER NOT NULL,
            shared_with_user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE,
            FOREIGN KEY (shared_with_user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(note_id, shared_with_user_id)
        )
    ''')

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
    # Приводим имя к нижнему регистру для уникальности
    username_lower = username.lower()
    try:
        cursor.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username_lower, password_hash))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_user_by_username(username: str):
    conn = get_connection()
    cursor = conn.cursor()
    # Ищем без учёта регистра
    cursor.execute('SELECT * FROM users WHERE LOWER(username) = ?', (username.lower(),))
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


def get_all_users():
    """Получить список всех пользователей (для выбора при расшаривании)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username FROM users ORDER BY username')
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return users


# === Сессии ===

def create_session(user_id: int, days=30):
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(days=days)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO sessions (id, user_id, expires_at) VALUES (?, ?, ?)',
                   (session_id, user_id, expires_at.isoformat()))
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

def get_all_notes_for_user(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT n.*, u.username as owner_username
        FROM notes n
        LEFT JOIN users u ON n.user_id = u.id
        WHERE n.user_id = ? 
           OR COALESCE(n.is_public, 0) = 1
           OR n.id IN (SELECT note_id FROM shared_notes WHERE shared_with_user_id = ?)
        ORDER BY n.created_at DESC
    ''', (user_id, user_id))
    notes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return notes

def get_notes_by_category_for_user(user_id: int, category: str):
    conn = get_connection()
    cursor = conn.cursor()
    if category:
        cursor.execute('''
            SELECT DISTINCT n.*, u.username as owner_username
            FROM notes n
            LEFT JOIN users u ON n.user_id = u.id
            WHERE (n.user_id = ? OR COALESCE(n.is_public, 0) = 1 OR n.id IN (SELECT note_id FROM shared_notes WHERE shared_with_user_id = ?))
              AND n.category = ?
            ORDER BY n.created_at DESC
        ''', (user_id, user_id, category))
    else:
        cursor.execute('''
            SELECT DISTINCT n.*, u.username as owner_username
            FROM notes n
            LEFT JOIN users u ON n.user_id = u.id
            WHERE n.user_id = ? OR COALESCE(n.is_public, 0) = 1 OR n.id IN (SELECT note_id FROM shared_notes WHERE shared_with_user_id = ?)
            ORDER BY n.created_at DESC
        ''', (user_id, user_id))
    notes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return notes

def search_notes_for_user(user_id: int, query: str, category: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    search_term = f"%{query.lower()}%"
    if category:
        cursor.execute('''
            SELECT DISTINCT n.*, u.username as owner_username
            FROM notes n
            LEFT JOIN users u ON n.user_id = u.id
            WHERE (n.user_id = ? OR COALESCE(n.is_public, 0) = 1 OR n.id IN (SELECT note_id FROM shared_notes WHERE shared_with_user_id = ?))
              AND n.category = ?
              AND (LOWER(n.title) LIKE ? OR LOWER(n.content) LIKE ?)
            ORDER BY n.created_at DESC
        ''', (user_id, user_id, category, search_term, search_term))
    else:
        cursor.execute('''
            SELECT DISTINCT n.*, u.username as owner_username
            FROM notes n
            LEFT JOIN users u ON n.user_id = u.id
            WHERE (n.user_id = ? OR COALESCE(n.is_public, 0) = 1 OR n.id IN (SELECT note_id FROM shared_notes WHERE shared_with_user_id = ?))
              AND (LOWER(n.title) LIKE ? OR LOWER(n.content) LIKE ?)
            ORDER BY n.created_at DESC
        ''', (user_id, user_id, search_term, search_term))
    notes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return notes

def get_all_categories(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT n.category FROM notes n
        LEFT JOIN shared_notes s ON n.id = s.note_id
        WHERE (n.user_id = ? OR n.is_public = 1 OR s.shared_with_user_id = ?)
          AND n.category != ""
        ORDER BY n.category
    ''', (user_id, user_id))
    categories = [row['category'] for row in cursor.fetchall()]
    conn.close()
    return categories


def add_note(user_id: int, title: str, content: str, category: str = "", image: str = "", is_public: int = 0):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO notes (user_id, title, content, category, image, is_public) VALUES (?, ?, ?, ?, ?, ?)',
        (user_id, title, content, category, image, is_public)
    )
    conn.commit()
    note_id = cursor.lastrowid
    conn.close()
    return note_id


def delete_note(note_id: int, user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT image FROM notes WHERE id = ? AND user_id = ?', (note_id, user_id))
    row = cursor.fetchone()
    if row and row['image']:
        filepath = os.path.join("uploads", row['image'])
        if os.path.exists(filepath):
            os.remove(filepath)
    cursor.execute('DELETE FROM notes WHERE id = ? AND user_id = ?', (note_id, user_id))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted > 0


def update_note(note_id: int, user_id: int, title: str, content: str, category: str = "", image: str = "",
                is_public: int = None):
    conn = get_connection()
    cursor = conn.cursor()
    if is_public is not None:
        cursor.execute(
            'UPDATE notes SET title = ?, content = ?, category = ?, image = ?, is_public = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?',
            (title, content, category, image, is_public, note_id, user_id)
        )
    else:
        cursor.execute(
            'UPDATE notes SET title = ?, content = ?, category = ?, image = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?',
            (title, content, category, image, note_id, user_id)
        )
    updated = cursor.rowcount
    conn.commit()
    conn.close()
    return updated > 0


def get_note_by_id(note_id: int, user_id: int):
    """Получить заметку (свою или доступную)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT n.*, u.username as owner_username
        FROM notes n
        LEFT JOIN users u ON n.user_id = u.id
        LEFT JOIN shared_notes s ON n.id = s.note_id
        WHERE n.id = ? AND (n.user_id = ? OR n.is_public = 1 OR s.shared_with_user_id = ?)
    ''', (note_id, user_id, user_id))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_note_image(note_id: int, user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT image FROM notes WHERE id = ? AND user_id = ?', (note_id, user_id))
    row = cursor.fetchone()
    conn.close()
    return row['image'] if row else None


# === Общий доступ ===

def share_note_with_users(note_id: int, owner_id: int, user_ids: list):
    """Поделиться заметкой с конкретными пользователями"""
    conn = get_connection()
    cursor = conn.cursor()
    # Проверяем, что заметка принадлежит владельцу
    cursor.execute('SELECT id FROM notes WHERE id = ? AND user_id = ?', (note_id, owner_id))
    if not cursor.fetchone():
        conn.close()
        return False

    # Удаляем старые расшаривания
    cursor.execute('DELETE FROM shared_notes WHERE note_id = ?', (note_id,))

    # Добавляем новые
    for uid in user_ids:
        if uid != owner_id:  # Не расшариваем самому себе
            try:
                cursor.execute('INSERT INTO shared_notes (note_id, shared_with_user_id) VALUES (?, ?)', (note_id, uid))
            except sqlite3.IntegrityError:
                pass  # Уже есть

    conn.commit()
    conn.close()
    return True


def get_shared_users(note_id: int, owner_id: int):
    """Получить список пользователей, с которыми расшарена заметка"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.id, u.username FROM users u
        JOIN shared_notes s ON u.id = s.shared_with_user_id
        WHERE s.note_id = ? AND (SELECT user_id FROM notes WHERE id = ?) = ?
    ''', (note_id, note_id, owner_id))
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return users


def set_note_public(note_id: int, owner_id: int, is_public: int):
    """Сделать заметку общей/приватной"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE notes SET is_public = ? WHERE id = ? AND user_id = ?', (is_public, note_id, owner_id))
    updated = cursor.rowcount
    conn.commit()
    conn.close()
    return updated > 0


init_db()