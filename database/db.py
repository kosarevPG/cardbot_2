# код/database/db.py
import logging
import json
from datetime import datetime
import psycopg2
import psycopg2.extras
from config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        """Инициализация соединения с PostgreSQL."""
        self.conn = None
        try:
            self.conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                dbname=DB_NAME
            )
            logger.info("Database connection established successfully.")
            self.bot = None
            self.create_schemas_and_tables()
        except psycopg2.OperationalError as e:
            logger.critical(f"Database connection failed: {e}", exc_info=True)
            raise

    def execute_query(self, query, params=None, fetch=None):
        """Универсальный метод для выполнения запросов."""
        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            try:
                cur.execute(query, params)
                self.conn.commit()
                if fetch == "one":
                    return cur.fetchone()
                if fetch == "all":
                    return cur.fetchall()
            except psycopg2.Error as e:
                logger.error(f"Database query failed: {e}\nQuery: {query}\nParams: {params}", exc_info=True)
                self.conn.rollback()
                return None

    def create_schemas_and_tables(self):
        """Создает схемы и таблицы, если они не существуют."""
        queries = [
            "CREATE SCHEMA IF NOT EXISTS core;",
            "CREATE SCHEMA IF NOT EXISTS programs;",
            "CREATE SCHEMA IF NOT EXISTS marketplace;",
            """
            CREATE TABLE IF NOT EXISTS core.users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                first_seen_at TIMESTAMPTZ DEFAULT NOW(),
                last_seen_at TIMESTAMPTZ DEFAULT NOW(),
                ozon_id TEXT,
                wildberries_id TEXT,
                bonus_available BOOLEAN DEFAULT FALSE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS core.actions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES core.users(user_id) ON DELETE CASCADE,
                action_type VARCHAR(50) NOT NULL,
                details JSONB,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """,
            # ... (здесь можно добавить остальные CREATE TABLE из вашего SQL скрипта)
        ]
        for query in queries:
            self.execute_query(query)
        logger.info("Schemas and tables checked/created successfully.")

    def get_user(self, user_id):
        """Получает данные пользователя или создает нового."""
        query = "SELECT * FROM core.users WHERE user_id = %s;"
        user = self.execute_query(query, (user_id,), fetch="one")
        if user:
            return dict(user)
        
        # Создаем нового пользователя
        insert_query = "INSERT INTO core.users (user_id) VALUES (%s) RETURNING *;"
        new_user = self.execute_query(insert_query, (user_id,), fetch="one")
        logger.info(f"New user created with ID: {user_id}")
        return dict(new_user) if new_user else None

    def update_user(self, user_id, data):
        """Обновляет данные пользователя."""
        # Убедимся, что пользователь существует
        self.get_user(user_id)
        
        # Формируем запрос на обновление
        set_clause = ", ".join([f"{key} = %s" for key in data.keys()])
        params = list(data.values()) + [user_id]
        query = f"UPDATE core.users SET {set_clause} WHERE user_id = %s;"
        self.execute_query(query, tuple(params))
        
        # Обновляем last_seen_at
        self.execute_query("UPDATE core.users SET last_seen_at = NOW() WHERE user_id = %s;", (user_id,))


    def save_action(self, user_id, username, name, action, details, timestamp):
        # Эта функция теперь проксирует вызов в новую систему логгирования
        self.log_action(user_id, action, details)


    def log_action(self, user_id, action_type, details=None):
        """Сохраняет действие пользователя в новой таблице core.actions."""
        details_json = json.dumps(details) if details else None
        query = "INSERT INTO core.actions (user_id, action_type, details) VALUES (%s, %s, %s);"
        self.execute_query(query, (user_id, action_type, details_json))

    def get_reminder_times(self):
        """Возвращает словарь {user_id: {'morning': time, 'evening': time}} для пользователей с установленными напоминаниями."""
        reminders = {}
        try:
            query = """
                SELECT user_id, reminder_time, reminder_time_evening
                FROM core.users WHERE reminder_time IS NOT NULL OR reminder_time_evening IS NOT NULL
            """
            result = self.execute_query(query, fetch="all")
            if result:
                for row in result:
                    reminders[row["user_id"]] = {
                        'morning': row["reminder_time"],
                        'evening': row["reminder_time_evening"]
                    }
            return reminders
        except Exception as e:
            logger.error(f"Failed to get reminder times: {e}", exc_info=True)
            return {}

    # ... Вам нужно будет адаптировать остальные методы (get_user_cards, add_referral и т.д.)
    # для работы с новыми таблицами и синтаксисом PostgreSQL.
    # Например:
    
    def add_user_card(self, user_id, card_number):
        """Добавляет запись об использованной карте."""
        query = "INSERT INTO programs.used_cards (user_id, card_number) VALUES (%s, %s);"
        self.execute_query(query, (user_id, card_number))

    def get_user_cards(self, user_id):
        """Возвращает список номеров карт, использованных пользователем."""
        query = "SELECT card_number FROM programs.used_cards WHERE user_id = %s;"
        result = self.execute_query(query, (user_id,), fetch="all")
        return [row['card_number'] for row in result] if result else []
        
    def close(self):
        """Закрывает соединение с базой данных."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed.")
