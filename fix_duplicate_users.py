import sqlite3

DB_NAME = "notebook.db"


def fix_duplicates():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Находим дубликаты (с одинаковым именем в нижнем регистре)
    cursor.execute('''
        SELECT LOWER(username) as lower_name, COUNT(*) as count, GROUP_CONCAT(id) as ids
        FROM users
        GROUP BY LOWER(username)
        HAVING count > 1
    ''')

    duplicates = cursor.fetchall()

    if not duplicates:
        print("✅ Дубликатов не найдено!")
        conn.close()
        return

    for lower_name, count, ids in duplicates:
        print(f"Найдено {count} пользователей с именем '{lower_name}': ID={ids}")

        # Оставляем первого (с наименьшим ID), остальных удаляем
        id_list = [int(x) for x in ids.split(',')]
        keep_id = min(id_list)
        delete_ids = [x for x in id_list if x != keep_id]

        print(f"  Оставляем ID={keep_id}, удаляем {delete_ids}")

        # Переносим заметки удаляемых пользователей к оставшемуся
        for del_id in delete_ids:
            cursor.execute('UPDATE notes SET user_id = ? WHERE user_id = ?', (keep_id, del_id))
            cursor.execute('UPDATE sessions SET user_id = ? WHERE user_id = ?', (keep_id, del_id))
            cursor.execute('UPDATE shared_notes SET shared_with_user_id = ? WHERE shared_with_user_id = ?',
                           (keep_id, del_id))
            cursor.execute('DELETE FROM users WHERE id = ?', (del_id,))

    conn.commit()
    conn.close()
    print("✅ Дубликаты удалены!")


if __name__ == "__main__":
    fix_duplicates()