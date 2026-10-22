import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta
DB_NAME = "notebook.db"


# === Подключение ===

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# === Инициализация базы данных ===

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN email TEXT')
        conn.commit()
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0')
        conn.commit()
    except sqlite3.OperationalError:
        pass

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

    # Таблица сброса пароля
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS password_resets (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
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

    # Таблица профилей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            avatar TEXT DEFAULT '',
            bio TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")


# === Пользователи ===

def create_user(username: str, email: str, password_hash: str):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Первый пользователь в системе становится администратором
        cursor.execute('SELECT COUNT(*) AS count FROM users')
        is_first_user = cursor.fetchone()['count'] == 0

        cursor.execute(
            'INSERT INTO users (username, email, password_hash, is_admin) VALUES (?, ?, ?, ?)',
            (username, email, password_hash, 1 if is_first_user else 0)
        )
        user_id = cursor.lastrowid
        cursor.execute('INSERT INTO profiles (user_id) VALUES (?)', (user_id,))
        conn.commit()
        return user_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_user_by_username(username: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE LOWER(username) = ?', (username.lower(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_email(email: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE LOWER(email) = ?', (email.lower(),))
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username FROM users ORDER BY username')
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return users


def update_user_password(user_id: int, new_password_hash: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_password_hash, user_id))
    conn.commit()
    conn.close()


# === Сессии ===

def create_session(user_id: int) -> str:
    session_id = str(uuid.uuid4())
    conn = get_connection()
    cursor = conn.cursor()
    # Сессия живёт 30 дней
    expires_at = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(
        'INSERT INTO sessions (id, user_id, expires_at) VALUES (?, ?, ?)',
        (session_id, user_id, expires_at)
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


# === Сброс пароля ===

def create_reset_token(user_id: int):
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(hours=1)  # Токен живёт 1 час
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM password_resets WHERE user_id = ?', (user_id,))
    cursor.execute(
        'INSERT INTO password_resets (token, user_id, expires_at) VALUES (?, ?, ?)',
        (token, user_id, expires_at.isoformat())
    )
    conn.commit()
    conn.close()
    return token


def get_user_by_reset_token(token: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.* FROM users u
        JOIN password_resets pr ON u.id = pr.user_id
        WHERE pr.token = ? AND pr.expires_at > ?
    ''', (token, datetime.now().isoformat()))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_reset_token(token: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM password_resets WHERE token = ?', (token,))
    conn.commit()
    conn.close()


# === Заметки ===

def get_all_notes_for_user(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT n.*, u.username AS owner_username
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
            SELECT DISTINCT n.*, u.username AS owner_username
            FROM notes n
            LEFT JOIN users u ON n.user_id = u.id
            WHERE (n.user_id = ? OR COALESCE(n.is_public, 0) = 1
                   OR n.id IN (SELECT note_id FROM shared_notes WHERE shared_with_user_id = ?))
              AND n.category = ?
            ORDER BY n.created_at DESC
        ''', (user_id, user_id, category))
    else:
        cursor.execute('''
            SELECT DISTINCT n.*, u.username AS owner_username
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


def search_notes_for_user(user_id: int, query: str, category: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    search_term = f"%{query.lower()}%"
    if category:
        cursor.execute('''
            SELECT DISTINCT n.*, u.username AS owner_username
            FROM notes n
            LEFT JOIN users u ON n.user_id = u.id
            WHERE (n.user_id = ? OR COALESCE(n.is_public, 0) = 1
                   OR n.id IN (SELECT note_id FROM shared_notes WHERE shared_with_user_id = ?))
              AND n.category = ?
              AND (LOWER(n.title) LIKE ? OR LOWER(n.content) LIKE ?)
            ORDER BY n.created_at DESC
        ''', (user_id, user_id, category, search_term, search_term))
    else:
        cursor.execute('''
            SELECT DISTINCT n.*, u.username AS owner_username
            FROM notes n
            LEFT JOIN users u ON n.user_id = u.id
            WHERE (n.user_id = ? OR COALESCE(n.is_public, 0) = 1
                   OR n.id IN (SELECT note_id FROM shared_notes WHERE shared_with_user_id = ?))
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
        SELECT DISTINCT n.category
        FROM notes n
        LEFT JOIN shared_notes s ON n.id = s.note_id
        WHERE (n.user_id = ? OR COALESCE(n.is_public, 0) = 1 OR s.shared_with_user_id = ?)
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


def update_note(note_id: int, user_id: int, title: str, content: str,
                category: str = "", image: str = "", is_public: int = None):
    conn = get_connection()
    cursor = conn.cursor()
    if is_public is not None:
        cursor.execute(
            '''UPDATE notes
               SET title = ?, content = ?, category = ?, image = ?, is_public = ?,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = ? AND user_id = ?''',
            (title, content, category, image, is_public, note_id, user_id)
        )
    else:
        cursor.execute(
            '''UPDATE notes
               SET title = ?, content = ?, category = ?, image = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ? AND user_id = ?''',
            (title, content, category, image, note_id, user_id)
        )
    updated = cursor.rowcount
    conn.commit()
    conn.close()
    return updated > 0


def get_note_by_id(note_id: int, user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT n.*, u.username AS owner_username
        FROM notes n
        LEFT JOIN users u ON n.user_id = u.id
        LEFT JOIN shared_notes s ON n.id = s.note_id
        WHERE n.id = ?
          AND (n.user_id = ? OR COALESCE(n.is_public, 0) = 1 OR s.shared_with_user_id = ?)
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM notes WHERE id = ? AND user_id = ?', (note_id, owner_id))
    if not cursor.fetchone():
        conn.close()
        return False
    cursor.execute('DELETE FROM shared_notes WHERE note_id = ?', (note_id,))
    for uid in user_ids:
        if uid != owner_id:
            try:
                cursor.execute(
                    'INSERT INTO shared_notes (note_id, shared_with_user_id) VALUES (?, ?)',
                    (note_id, uid)
                )
            except sqlite3.IntegrityError:
                pass
    conn.commit()
    conn.close()
    return True


def get_shared_users(note_id: int, owner_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.id, u.username
        FROM users u
        JOIN shared_notes s ON u.id = s.shared_with_user_id
        WHERE s.note_id = ? AND (SELECT user_id FROM notes WHERE id = ?) = ?
    ''', (note_id, note_id, owner_id))
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return users


def set_note_public(note_id: int, owner_id: int, is_public: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE notes SET is_public = ? WHERE id = ? AND user_id = ?', (is_public, note_id, owner_id))
    updated = cursor.rowcount
    conn.commit()
    conn.close()
    return updated > 0


# === Профили ===

def get_profile(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM profiles WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def create_profile(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO profiles (user_id) VALUES (?)', (user_id,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def update_profile(user_id: int, bio: str = None, avatar: str = None):
    conn = get_connection()
    cursor = conn.cursor()

    # Собираем только те поля, которые переданы (не None)
    updates = []
    params = []

    if bio is not None:
        updates.append('bio = ?')
        params.append(bio)

    if avatar is not None:
        updates.append('avatar = ?')
        params.append(avatar)

    if not updates:
        conn.close()
        return False

    updates.append('updated_at = CURRENT_TIMESTAMP')
    params.append(user_id)

    query = 'UPDATE profiles SET ' + ', '.join(updates) + ' WHERE user_id = ?'
    cursor.execute(query, params)
    updated = cursor.rowcount
    conn.commit()
    conn.close()
    return updated > 0


# === Администрирование ===

def set_admin(user_id: int, is_admin: bool):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_admin = ? WHERE id = ?', (1 if is_admin else 0, user_id))
    updated = cursor.rowcount
    conn.commit()
    conn.close()
    return updated > 0


def is_admin(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT is_admin FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row and row['is_admin'])


def get_stats():
    """Получить общую статистику для админки"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) AS count FROM users')
    users_count = cursor.fetchone()['count']

    cursor.execute('SELECT COUNT(*) AS count FROM notes')
    notes_count = cursor.fetchone()['count']

    cursor.execute('SELECT COUNT(*) AS count FROM notes WHERE image != ""')
    photos_count = cursor.fetchone()['count']

    cursor.execute('SELECT COUNT(*) AS count FROM profiles WHERE avatar != ""')
    avatars_count = cursor.fetchone()['count']

    conn.close()

    return {
        'users_count': users_count,
        'notes_count': notes_count,
        'photos_count': photos_count,
        'avatars_count': avatars_count
    }


def get_all_users_with_stats():
    """Получить список всех пользователей с их статистикой"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.id, u.username, u.email, u.is_admin, u.created_at,
               COUNT(n.id) AS notes_count
        FROM users u
        LEFT JOIN notes n ON u.id = n.user_id
        GROUP BY u.id
        ORDER BY u.created_at DESC
    ''')
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return users


def delete_user(user_id: int):
    """Удалить пользователя и все его данные"""
    conn = get_connection()
    cursor = conn.cursor()

    # Явно удаляем все заметки пользователя (на всякий случай)
    cursor.execute('SELECT id, image FROM notes WHERE user_id = ?', (user_id,))
    notes = cursor.fetchall()

    for note in notes:
        # Удаляем фото заметки
        if note['image']:
            img_path = os.path.join("uploads", note['image'])
            if os.path.exists(img_path):
                os.remove(img_path)

        # Удаляем записи в shared_notes
        cursor.execute('DELETE FROM shared_notes WHERE note_id = ?', (note['id'],))

    # Удаляем аватарку
    cursor.execute('SELECT avatar FROM profiles WHERE user_id = ?', (user_id,))
    profile = cursor.fetchone()
    if profile and profile['avatar']:
        avatar_path = os.path.join("avatars", profile['avatar'])
        if os.path.exists(avatar_path):
            os.remove(avatar_path)

    # Удаляем все заметки пользователя
    cursor.execute('DELETE FROM notes WHERE user_id = ?', (user_id,))

    # Удаляем записи в shared_notes, где пользователь был получателем
    cursor.execute('DELETE FROM shared_notes WHERE shared_with_user_id = ?', (user_id,))

    # Удаляем профиль
    cursor.execute('DELETE FROM profiles WHERE user_id = ?', (user_id,))

    # Удаляем сессии
    cursor.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))

    # Удаляем токены сброса пароля
    cursor.execute('DELETE FROM password_resets WHERE user_id = ?', (user_id,))

    # Наконец удаляем самого пользователя
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    deleted = cursor.rowcount

    conn.commit()
    conn.close()
    return deleted > 0


init_db()