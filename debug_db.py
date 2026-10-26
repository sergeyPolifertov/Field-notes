import sqlite3

conn = sqlite3.connect('notebook.db')
cursor = conn.cursor()

# Смотрим, что реально лежит в базе после "очистки"
cursor.execute("SELECT id, title, category FROM notes LIMIT 5")
print("=== ЗАМЕТКИ В БАЗЕ ===")
for row in cursor.fetchall():
    print(f"ID: {row[0]}, Title: {row[1]}, Category/Tags: '{row[2]}'")

# Проверяем, есть ли вообще заметки у текущего юзера
cursor.execute("SELECT COUNT(*) FROM notes WHERE user_id = 1")  # Замени 1 на свой ID
print(f"\nВсего заметок у пользователя: {cursor.fetchone()[0]}")

conn.close()