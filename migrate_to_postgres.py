import sqlite3
import psycopg2
import psycopg2.extras
import json
import os
from dotenv import load_dotenv
from datetime import datetime

# Загружаем переменные окружения из .env файла
load_dotenv()

# --- Настройки подключения ---
SQLITE_DB_PATH = os.path.join("data", "bot (6).db") # Путь к вашей старой базе

PG_HOST = os.getenv("DB_HOST")
PG_PORT = os.getenv("DB_PORT")
PG_USER = os.getenv("DB_USER")
PG_PASSWORD = os.getenv("DB_PASSWORD")
PG_DBNAME = os.getenv("DB_NAME")

print("--- Начало миграции данных из SQLite в PostgreSQL ---")

# --- Подключение к базам данных ---
try:
    print(f"Подключаюсь к SQLite: {SQLITE_DB_PATH}")
    sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()
    print("✓ Успешное подключение к SQLite.")
except Exception as e:
    print(f"❌ Ошибка подключения к SQLite: {e}")
    exit()

try:
    print(f"Подключаюсь к PostgreSQL: {PG_HOST}:{PG_PORT}/{PG_DBNAME}")
    pg_conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=PG_USER,
        password=PG_PASSWORD,
        dbname=PG_DBNAME
    )
    pg_cur = pg_conn.cursor()
    print("✓ Успешное подключение к PostgreSQL.")
except Exception as e:
    print(f"❌ Ошибка подключения к PostgreSQL: {e}")
    exit()

# --- Функция-помощник для обработки данных ---
def parse_timestamp(ts_str):
    if not ts_str:
        return None
    try:
        # Универсальная обработка разных форматов
        if isinstance(ts_str, datetime):
            return ts_str
        ts_str = ts_str.replace('Z', '+00:00')
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        print(f"  > Предупреждение: не удалось разобрать дату '{ts_str}', будет вставлено NULL.")
        return None

# --- Миграция таблицы users ---
try:
    print("\n[1/5] Миграция пользователей (core.users)...")
    sqlite_cur.execute("SELECT * FROM users;")
    users = sqlite_cur.fetchall()
    
    insert_query = """
    INSERT INTO core.users (user_id, username, full_name, last_seen_at, bonus_available)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (user_id) DO UPDATE SET
        username = EXCLUDED.username,
        full_name = EXCLUDED.full_name,
        last_seen_at = EXCLUDED.last_seen_at,
        bonus_available = EXCLUDED.bonus_available;
    """
    
    users_to_insert = []
    for user in users:
        users_to_insert.append((
            user['user_id'],
            user['username'],
            user['name'], # В новой схеме это 'full_name'
            parse_timestamp(user['last_request']), # В новой схеме это 'last_seen_at'
            bool(user['bonus_available'])
        ))
    
    psycopg2.extras.execute_batch(pg_cur, insert_query, users_to_insert)
    pg_conn.commit()
    print(f"✓ Успешно перенесено {len(users_to_insert)} пользователей.")

except Exception as e:
    pg_conn.rollback()
    print(f"❌ Ошибка при миграции пользователей: {e}")


# --- Миграция таблицы actions ---
try:
    print("\n[2/5] Миграция действий (core.actions)...")
    sqlite_cur.execute("SELECT * FROM actions;")
    actions = sqlite_cur.fetchall()
    
    insert_query = """
    INSERT INTO core.actions (user_id, action_type, details, created_at)
    VALUES (%s, %s, %s, %s);
    """
    
    actions_to_insert = []
    for action in actions:
        details = None
        try:
            # Убедимся, что details - это валидный JSON
            if action['details']:
                details = json.dumps(json.loads(action['details']))
        except (json.JSONDecodeError, TypeError):
            details = json.dumps({'raw_details': action['details']})

        actions_to_insert.append((
            action['user_id'],
            action['action'], # В новой схеме это 'action_type'
            details,
            parse_timestamp(action['timestamp']) # В новой схеме это 'created_at'
        ))

    psycopg2.extras.execute_batch(pg_cur, insert_query, actions_to_insert)
    pg_conn.commit()
    print(f"✓ Успешно перенесено {len(actions_to_insert)} действий.")

except Exception as e:
    pg_conn.rollback()
    print(f"❌ Ошибка при миграции действий: {e}")


# --- Миграция таблицы referrals ---
try:
    print("\n[3/5] Миграция рефералов (core.referrals)...")
    sqlite_cur.execute("SELECT * FROM referrals;")
    referrals = sqlite_cur.fetchall()
    
    insert_query = """
    INSERT INTO core.referrals (referrer_id, referred_id)
    VALUES (%s, %s) ON CONFLICT DO NOTHING;
    """
    
    referrals_to_insert = [(ref['referrer_id'], ref['referred_id']) for ref in referrals]
    psycopg2.extras.execute_batch(pg_cur, insert_query, referrals_to_insert)
    pg_conn.commit()
    print(f"✓ Успешно перенесено {len(referrals_to_insert)} реферальных связей.")

except Exception as e:
    pg_conn.rollback()
    print(f"❌ Ошибка при миграции рефералов: {e}")

# --- Миграция таблицы user_cards ---
try:
    print("\n[4/5] Миграция использованных карт (programs.used_cards)...")
    sqlite_cur.execute("SELECT * FROM user_cards;")
    cards = sqlite_cur.fetchall()
    
    insert_query = """
    INSERT INTO programs.used_cards (user_id, card_number)
    VALUES (%s, %s);
    """
    
    cards_to_insert = [(card['user_id'], card['card_number']) for card in cards]
    psycopg2.extras.execute_batch(pg_cur, insert_query, cards_to_insert)
    pg_conn.commit()
    print(f"✓ Успешно перенесено {len(cards_to_insert)} записей о картах.")

except Exception as e:
    pg_conn.rollback()
    print(f"❌ Ошибка при миграции карт: {e}")

# --- Миграция таблицы feedback ---
try:
    print("\n[5/5] Миграция обратной связи (core.feedback)...")
    sqlite_cur.execute("SELECT * FROM feedback;")
    feedbacks = sqlite_cur.fetchall()
    
    insert_query = """
    INSERT INTO core.feedback (user_id, feedback_text, created_at)
    VALUES (%s, %s, %s);
    """
    
    feedback_to_insert = []
    for fb in feedbacks:
        feedback_to_insert.append((
            fb['user_id'],
            fb['feedback'],
            parse_timestamp(fb['timestamp'])
        ))
    
    psycopg2.extras.execute_batch(pg_cur, insert_query, feedback_to_insert)
    pg_conn.commit()
    print(f"✓ Успешно перенесено {len(feedback_to_insert)} отзывов.")
    
except Exception as e:
    pg_conn.rollback()
    print(f"❌ Ошибка при миграции обратной связи: {e}")


# --- Завершение ---
sqlite_conn.close()
pg_conn.close()
print("\n--- Миграция завершена! ---") 