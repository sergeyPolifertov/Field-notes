import sqlite3

DB_NAME = "notebook.db"


def check():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    print("=== ПОЛЬЗОВАТЕЛИ ===")
    cursor.execute('SELECT id, username FROM users')
    for row in cursor.fetchall():
        print(f"  ID={row[0]}, Имя={row[1]}")

    print("\n=== ЗАМЕТКИ ===")
    cursor.execute('SELECT id, user_id, title, is_public FROM notes ORDER BY id')
    for row in cursor.fetchall():
        print(f"  ID={row[0]}, user_id={row[1]}, title='{row[2]}', is_public={row[3]}")

    print("\n=== СЕССИИ ===")
    cursor.execute('SELECT id, user_id FROM sessions')
    for row in cursor.fetchall():
        print(f"  session={row[0][:20]}..., user_id={row[1]}")

    conn.close()


if __name__ == "__main__":
    check()