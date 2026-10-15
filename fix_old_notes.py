import sqlite3

DB_NAME = "notebook.db"


def fix_old_notes():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Устанавливаем is_public = 0 для всех заметок где оно NULL
    cursor.execute('UPDATE notes SET is_public = 0 WHERE is_public IS NULL')
    updated = cursor.rowcount

    conn.commit()
    conn.close()

    print(f"✅ Обновлено заметок: {updated}")


if __name__ == "__main__":
    fix_old_notes()