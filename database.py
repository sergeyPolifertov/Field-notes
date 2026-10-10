import sqlite3
import os
from datetime import datetime

DB_NAME = "notebook.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Таблица заметок с полем category
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Если таблица уже есть без поля category — добавляем его
    try:
        cursor.execute('ALTER TABLE notes ADD COLUMN category TEXT DEFAULT ""')
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Поле уже существует

    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")


def get_all_notes():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM notes ORDER BY created_at DESC')
    notes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return notes


def get_notes_by_category(category: str):
    """Получить заметки по категории (пустая строка = все)"""
    conn = get_connection()
    cursor = conn.cursor()
    if category:
        cursor.execute(
            'SELECT * FROM notes WHERE category = ? ORDER BY created_at DESC',
            (category,)
        )
    else:
        cursor.execute('SELECT * FROM notes ORDER BY created_at DESC')
    notes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return notes


def search_notes(query: str, category: str = ""):
    """Поиск заметок по заголовку и содержимому (регистронезависимый)"""
    conn = get_connection()
    cursor = conn.cursor()
    search_term = f"%{query.lower()}%"
    if category:
        cursor.execute(
            '''SELECT * FROM notes 
               WHERE (LOWER(title) LIKE ? OR LOWER(content) LIKE ?) 
               AND category = ?
               ORDER BY created_at DESC''',
            (search_term, search_term, category)
        )
    else:
        cursor.execute(
            '''SELECT * FROM notes 
               WHERE LOWER(title) LIKE ? OR LOWER(content) LIKE ?
               ORDER BY created_at DESC''',
            (search_term, search_term)
        )
    notes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return notes


def get_all_categories():
    """Получить список всех используемых категорий"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT DISTINCT category FROM notes WHERE category != "" ORDER BY category'
    )
    categories = [row['category'] for row in cursor.fetchall()]
    conn.close()
    return categories


def add_note(title: str, content: str, category: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO notes (title, content, category) VALUES (?, ?, ?)',
        (title, content, category)
    )
    conn.commit()
    note_id = cursor.lastrowid
    conn.close()
    return note_id


def delete_note(note_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM notes WHERE id = ?', (note_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted > 0


def update_note(note_id: int, title: str, content: str, category: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE notes SET title = ?, content = ?, category = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (title, content, category, note_id)
    )
    updated = cursor.rowcount
    conn.commit()
    conn.close()
    return updated > 0


def get_note_by_id(note_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM notes WHERE id = ?', (note_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


init_db()