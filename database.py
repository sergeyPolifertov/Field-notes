import sqlite3
import os
from datetime import datetime

DB_NAME = "notebook.db"

def get_connection():
    """Получить соединение с базой данных"""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # Чтобы получать данные как словари
    return conn

def init_db():
    """Создать таблицу, если её нет"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

def get_all_notes():
    """Получить все заметки (новые сверху)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM notes ORDER BY created_at DESC')
    notes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return notes

def add_note(title: str, content: str):
    """Добавить новую заметку"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO notes (title, content) VALUES (?, ?)',
        (title, content)
    )
    conn.commit()
    note_id = cursor.lastrowid
    conn.close()
    return note_id

def delete_note(note_id: int):
    """Удалить заметку по ID"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM notes WHERE id = ?', (note_id,))
    conn.commit()
    deleted = cursor.rowcount
    conn.close()
    return deleted > 0

def update_note(note_id: int, title: str, content: str):
    """Обновить заметку"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE notes SET title = ?, content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (title, content, note_id)
    )
    conn.commit()
    updated = cursor.rowcount
    conn.close()
    return updated > 0

def get_note_by_id(note_id: int):
    """Получить одну заметку по ID"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM notes WHERE id = ?', (note_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

# Инициализируем БД при импорте
init_db()