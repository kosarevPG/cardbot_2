import json
import os
import sqlite3
from datetime import datetime
from config import TIMEZONE
from database.db import Database

# Пути к JSON-файлам (в директории data/)
JSON_FILES = {
    "last_request": "data/last_request.json",
    "user_names": "data/user_names.json",
    "referrals": "data/referrals.json",
    "bonus_available": "data/bonus_available.json",
    "reminder_times": "data/reminder_times.json",
    "user_actions": "data/user_actions.json",
    "user_cards": "data/user_cards.json"
}

def load_json(file_path, default):
    """Загрузка данных из JSON-файла."""
    if not os.path.exists(file_path):
        print(f"Файл {file_path} не найден, используется значение по умолчанию: {default}")
        return default
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return {int(k) if k.isdigit() else k: v for k, v in data.items()}
            return data
    except json.JSONDecodeError as e:
        print(f"Ошибка декодирования JSON в файле {file_path}: {e}")
        return default
    except Exception as e:
        print(f"Неизвестная ошибка при загрузке {file_path}: {e}")
        return default

def migrate_data():
    """Миграция данных из JSON в SQLite."""
    # Создаём директорию database/, если она не существует
    db_path = "database/bot.db"  # Локальный путь для миграции
    db_dir = os.path.dirname(db_path)
    if not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir, exist_ok=True)
            print(f"Создана директория {db_dir}")
        except Exception as e:
            print(f"Не удалось создать директорию {db_dir}: {e}")
            return

    # Инициализация базы данных
    try:
        db = Database(path=db_path)
    except Exception as e:
        print(f"Не удалось открыть базу данных {db_path}: {e}")
        return

    conn = db.conn
    conn.row_factory = sqlite3.Row

    # 1. Миграция LAST_REQUEST (последние запросы карт)
    last_requests = load_json(JSON_FILES["last_request"], {})
    for user_id, timestamp in last_requests.items():
        try:
            # Преобразуем строку timestamp в объект datetime
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(TIMEZONE)
            conn.execute("""
                INSERT OR IGNORE INTO users (user_id, last_request)
                VALUES (?, ?)
            """, (int(user_id), dt.isoformat()))
        except ValueError as e:
            print(f"Ошибка преобразования времени для user_id {user_id}: {e}")
    print("Миграция LAST_REQUEST завершена.")

    # 2. Миграция USER_NAMES (имена пользователей)
    user_names = load_json(JSON_FILES["user_names"], {})
    for user_id, name in user_names.items():
        conn.execute("""
            INSERT OR REPLACE INTO users (user_id, name)
            VALUES (?, ?)
        """, (int(user_id), name))
    print("Миграция USER_NAMES завершена.")

    # 3. Миграция REFERRALS (реферальные связи)
    referrals = load_json(JSON_FILES["referrals"], {})
    for referrer_id, referred_ids in referrals.items():
        for referred_id in referred_ids:
            conn.execute("""
                INSERT OR IGNORE INTO referrals (referrer_id, referred_id)
                VALUES (?, ?)
            """, (int(referrer_id), int(referred_id)))
    print("Миграция REFERRALS завершена.")

    # 4. Миграция BONUS_AVAILABLE (доступность бонусов)
    bonus_available = load_json(JSON_FILES["bonus_available"], {})
    for user_id, available in bonus_available.items():
        conn.execute("""
            UPDATE users SET bonus_available = ?
            WHERE user_id = ?
        """, (int(available), int(user_id)))
    print("Миграция BONUS_AVAILABLE завершена.")

    # 5. Миграция REMINDER_TIMES (время напоминаний)
    reminder_times = load_json(JSON_FILES["reminder_times"], {})
    for user_id, reminder_time in reminder_times.items():
        conn.execute("""
            UPDATE users SET reminder_time = ?
            WHERE user_id = ?
        """, (reminder_time, int(user_id)))
    print("Миграция REMINDER_TIMES завершена.")

    # 6. Миграция USER_ACTIONS (действия пользователей)
    user_actions = load_json(JSON_FILES["user_actions"], [])
    for action in user_actions:
        user_id = int(action["user_id"])
        username = action.get("username", "")
        name = action.get("name", "")
        action_type = action["action"]
        details = action.get("details", {})
        timestamp = action["timestamp"]

        conn.execute("""
            INSERT INTO actions (user_id, username, name, action, details, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, username, name, action_type, json.dumps(details), timestamp))
    print("Миграция USER_ACTIONS завершена.")

    # 7. Миграция USER_CARDS (использованные карты)
    user_cards = load_json(JSON_FILES["user_cards"], {})
    for user_id, cards in user_cards.items():
        for card_number in cards:
            conn.execute("""
                INSERT OR IGNORE INTO user_cards (user_id, card_number)
                VALUES (?, ?)
            """, (int(user_id), int(card_number)))
    print("Миграция USER_CARDS завершена.")

    # Сохранение изменений
    conn.commit()
    print("Миграция всех данных успешно завершена!")

def verify_migration():
    """Проверка корректности миграции."""
    db_path = "database/bot.db"
    try:
        db = Database(path=db_path)
    except Exception as e:
        print(f"Не удалось открыть базу данных для проверки {db_path}: {e}")
        return

    conn = db.conn

    # Проверка пользователей
    cursor = conn.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    print(f"Количество пользователей в базе: {user_count}")

    # Проверка действий
    cursor = conn.execute("SELECT COUNT(*) FROM actions")
    action_count = cursor.fetchone()[0]
    print(f"Количество действий в базе: {action_count}")

    # Проверка карт
    cursor = conn.execute("SELECT COUNT(*) FROM user_cards")
    card_count = cursor.fetchone()[0]
    print(f"Количество использованных карт: {card_count}")

    # Проверка рефералов
    cursor = conn.execute("SELECT COUNT(*) FROM referrals")
    referral_count = cursor.fetchone()[0]
    print(f"Количество реферальных записей: {referral_count}")

if __name__ == "__main__":
    # Выполняем миграцию
    migrate_data()

    # Проверяем результат
    verify_migration()
