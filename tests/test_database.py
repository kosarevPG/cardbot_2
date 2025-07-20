# -*- coding: utf-8 -*-
"""
Тесты для работы с базой данных.
"""

import pytest
import sqlite3
from datetime import datetime, date
from database.db import Database


class TestDatabase:
    """Тесты для класса Database."""

    def test_database_initialization(self, test_database):
        """Тест инициализации базы данных."""
        assert test_database is not None
        assert test_database.conn is not None
        assert isinstance(test_database.conn, sqlite3.Connection)

    def test_tables_creation(self, test_database):
        """Тест создания таблиц."""
        cursor = test_database.conn.cursor()
        
        # Проверяем существование таблиц
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        expected_tables = ['users', 'user_cards', 'user_actions', 'evening_reflections']
        for table in expected_tables:
            assert table in tables, f"Таблица {table} не найдена"

    def test_user_creation(self, test_database, sample_user_data):
        """Тест создания пользователя."""
        user_id = sample_user_data["id"]
        
        # Создаем пользователя
        test_database.create_user(
            user_id=user_id,
            username=sample_user_data["username"],
            name=sample_user_data["name"]
        )
        
        # Проверяем, что пользователь создан
        user = test_database.get_user(user_id)
        assert user is not None
        assert user["id"] == user_id
        assert user["username"] == sample_user_data["username"]
        assert user["name"] == sample_user_data["name"]

    def test_user_update(self, test_database, sample_user_data):
        """Тест обновления пользователя."""
        user_id = sample_user_data["id"]
        
        # Создаем пользователя
        test_database.create_user(
            user_id=user_id,
            username=sample_user_data["username"],
            name=sample_user_data["name"]
        )
        
        # Обновляем данные
        new_name = "Updated Name"
        test_database.update_user(user_id, {"name": new_name})
        
        # Проверяем обновление
        user = test_database.get_user(user_id)
        assert user["name"] == new_name

    def test_card_creation(self, test_database, sample_user_data, sample_card_data):
        """Тест создания карты."""
        user_id = sample_user_data["id"]
        
        # Создаем пользователя
        test_database.create_user(
            user_id=user_id,
            username=sample_user_data["username"],
            name=sample_user_data["name"]
        )
        
        # Создаем карту
        test_database.save_user_card(
            user_id=sample_card_data["user_id"],
            date=sample_card_data["date"],
            card_number=sample_card_data["card_number"],
            user_request=sample_card_data["user_request"],
            initial_resource=sample_card_data["initial_resource"],
            final_resource=sample_card_data["final_resource"],
            recharge_method=sample_card_data["recharge_method"]
        )
        
        # Проверяем создание карты
        cards = test_database.get_user_cards(user_id)
        assert len(cards) == 1
        card = cards[0]
        assert card["user_id"] == user_id
        assert card["card_number"] == sample_card_data["card_number"]
        assert card["user_request"] == sample_card_data["user_request"]

    def test_card_availability(self, test_database, sample_user_data, sample_card_data):
        """Тест проверки доступности карты."""
        user_id = sample_user_data["id"]
        card_date = sample_card_data["date"]
        
        # Создаем пользователя
        test_database.create_user(
            user_id=user_id,
            username=sample_user_data["username"],
            name=sample_user_data["name"]
        )
        
        # Проверяем доступность карты (должна быть доступна)
        assert test_database.is_card_available(user_id, date.fromisoformat(card_date))
        
        # Создаем карту
        test_database.save_user_card(
            user_id=sample_card_data["user_id"],
            date=sample_card_data["date"],
            card_number=sample_card_data["card_number"],
            user_request=sample_card_data["user_request"],
            initial_resource=sample_card_data["initial_resource"],
            final_resource=sample_card_data["final_resource"],
            recharge_method=sample_card_data["recharge_method"]
        )
        
        # Проверяем, что карта больше не доступна
        assert not test_database.is_card_available(user_id, date.fromisoformat(card_date))

    def test_reflection_creation(self, test_database, sample_user_data, sample_reflection_data):
        """Тест создания рефлексии."""
        user_id = sample_user_data["id"]
        
        # Создаем пользователя
        test_database.create_user(
            user_id=user_id,
            username=sample_user_data["username"],
            name=sample_user_data["name"]
        )
        
        # Создаем рефлексию
        test_database.save_evening_reflection(
            user_id=sample_reflection_data["user_id"],
            date=sample_reflection_data["date"],
            good_moments=sample_reflection_data["good_moments"],
            gratitude=sample_reflection_data["gratitude"],
            hard_moments=sample_reflection_data["hard_moments"],
            ai_summary=sample_reflection_data["ai_summary"]
        )
        
        # Проверяем создание рефлексии
        reflections = test_database.get_evening_reflections(user_id)
        assert len(reflections) == 1
        reflection = reflections[0]
        assert reflection["user_id"] == user_id
        assert reflection["good_moments"] == sample_reflection_data["good_moments"]
        assert reflection["gratitude"] == sample_reflection_data["gratitude"]

    def test_action_logging(self, test_database, sample_user_data):
        """Тест логирования действий."""
        user_id = sample_user_data["id"]
        
        # Создаем пользователя
        test_database.create_user(
            user_id=user_id,
            username=sample_user_data["username"],
            name=sample_user_data["name"]
        )
        
        # Логируем действие
        action = "test_action"
        details = {"test": "data"}
        test_database.log_action(user_id, action, details)
        
        # Проверяем логирование
        actions = test_database.get_actions(user_id)
        assert len(actions) == 1
        logged_action = actions[0]
        assert logged_action["user_id"] == user_id
        assert logged_action["action"] == action
        assert logged_action["details"] == details

    def test_get_all_users(self, test_database, sample_user_data):
        """Тест получения всех пользователей."""
        user_id = sample_user_data["id"]
        
        # Создаем пользователя
        test_database.create_user(
            user_id=user_id,
            username=sample_user_data["username"],
            name=sample_user_data["name"]
        )
        
        # Получаем всех пользователей
        users = test_database.get_all_users()
        assert len(users) == 1
        assert user_id in users

    def test_reminder_times(self, test_database, sample_user_data):
        """Тест работы с временем напоминаний."""
        user_id = sample_user_data["id"]
        
        # Создаем пользователя
        test_database.create_user(
            user_id=user_id,
            username=sample_user_data["username"],
            name=sample_user_data["name"]
        )
        
        # Устанавливаем время напоминаний
        morning_time = "09:00"
        evening_time = "21:00"
        test_database.update_user(user_id, {
            "reminder_time": morning_time,
            "reminder_time_evening": evening_time
        })
        
        # Получаем время напоминаний
        reminder_times = test_database.get_reminder_times()
        assert user_id in reminder_times
        assert reminder_times[user_id]["morning"] == morning_time
        assert reminder_times[user_id]["evening"] == evening_time

    def test_referral_system(self, test_database, sample_user_data):
        """Тест реферальной системы."""
        referrer_id = sample_user_data["id"]
        referred_id = 987654321
        
        # Создаем реферера
        test_database.create_user(
            user_id=referrer_id,
            username=sample_user_data["username"],
            name=sample_user_data["name"]
        )
        
        # Создаем реферала
        test_database.create_user(
            user_id=referred_id,
            username="referred_user",
            name="Referred User"
        )
        
        # Добавляем реферала
        result = test_database.add_referral(referrer_id, referred_id)
        assert result is True
        
        # Проверяем, что повторное добавление возвращает False
        result = test_database.add_referral(referrer_id, referred_id)
        assert result is False

    def test_bonus_availability(self, test_database, sample_user_data):
        """Тест доступности бонуса."""
        user_id = sample_user_data["id"]
        
        # Создаем пользователя
        test_database.create_user(
            user_id=user_id,
            username=sample_user_data["username"],
            name=sample_user_data["name"]
        )
        
        # Проверяем, что бонус изначально недоступен
        user = test_database.get_user(user_id)
        assert not user.get("bonus_available", False)
        
        # Устанавливаем бонус доступным
        test_database.update_user(user_id, {"bonus_available": True})
        
        # Проверяем, что бонус стал доступен
        user = test_database.get_user(user_id)
        assert user.get("bonus_available", False)

    def test_database_connection_error(self):
        """Тест обработки ошибок подключения к БД."""
        with pytest.raises(Exception):
            # Пытаемся создать БД в несуществующей директории
            Database(path="/non/existent/path/db.db")

    def test_invalid_user_id(self, test_database):
        """Тест работы с некорректным ID пользователя."""
        # Пытаемся получить несуществующего пользователя
        user = test_database.get_user(999999999)
        assert user is None

    def test_database_close(self, test_database):
        """Тест закрытия соединения с БД."""
        test_database.close()
        # Проверяем, что соединение закрыто
        with pytest.raises(sqlite3.ProgrammingError):
            test_database.conn.execute("SELECT 1") 