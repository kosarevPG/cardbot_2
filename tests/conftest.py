# -*- coding: utf-8 -*-
"""
Общие фикстуры и утилиты для тестов.
"""

import pytest
import asyncio
import tempfile
import os
import sqlite3
from unittest.mock import MagicMock, AsyncMock, patch
from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery, User, Chat
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# Импорты из проекта
from database.db import Database
from modules.logging_service import LoggingService
from modules.notification_service import NotificationService
from modules.user_management import UserManager


@pytest.fixture(scope="session")
def event_loop():
    """Создает event loop для асинхронных тестов."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_db_path():
    """Создает временный путь для тестовой базы данных."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    yield db_path
    # Очистка после теста
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def test_database(temp_db_path):
    """Создает тестовую базу данных."""
    db = Database(path=temp_db_path)
    yield db
    db.close()


@pytest.fixture
def mock_bot():
    """Создает mock-объект для Bot."""
    bot = MagicMock(spec=Bot)
    bot.send_message = AsyncMock()
    bot.send_chat_action = AsyncMock()
    bot.get_chat_member = AsyncMock()
    return bot


@pytest.fixture
def mock_dispatcher():
    """Создает mock-объект для Dispatcher."""
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    return dp


@pytest.fixture
def mock_message():
    """Создает mock-объект для Message."""
    message = MagicMock(spec=Message)
    message.from_user = MagicMock(spec=User)
    message.from_user.id = 123456789
    message.from_user.username = "test_user"
    message.from_user.first_name = "Test"
    message.from_user.last_name = "User"
    message.chat = MagicMock(spec=Chat)
    message.chat.id = 123456789
    message.chat.type = "private"
    message.text = "/start"
    message.answer = AsyncMock()
    message.reply = AsyncMock()
    message.bot = MagicMock(spec=Bot)
    message.bot.send_chat_action = AsyncMock()
    return message


@pytest.fixture
def mock_callback_query():
    """Создает mock-объект для CallbackQuery."""
    callback = MagicMock(spec=CallbackQuery)
    callback.from_user = MagicMock(spec=User)
    callback.from_user.id = 123456789
    callback.from_user.username = "test_user"
    callback.data = "test_callback"
    callback.message = MagicMock(spec=Message)
    callback.message.chat.id = 123456789
    callback.answer = AsyncMock()
    callback.message.edit_reply_markup = AsyncMock()
    return callback


@pytest.fixture
def mock_fsm_context():
    """Создает mock-объект для FSMContext."""
    context = MagicMock(spec=FSMContext)
    context.set_state = AsyncMock()
    context.clear = AsyncMock()
    context.update_data = AsyncMock()
    context.get_data = AsyncMock(return_value={})
    return context


@pytest.fixture
def mock_logging_service(test_database):
    """Создает mock-объект для LoggingService."""
    service = MagicMock(spec=LoggingService)
    service.log_action = AsyncMock()
    return service


@pytest.fixture
def mock_notification_service(mock_bot, test_database):
    """Создает mock-объект для NotificationService."""
    service = MagicMock(spec=NotificationService)
    service.bot = mock_bot
    service.db = test_database
    service.check_reminders = AsyncMock()
    service.send_broadcast = AsyncMock()
    return service


@pytest.fixture
def mock_user_manager(test_database):
    """Создает mock-объект для UserManager."""
    manager = MagicMock(spec=UserManager)
    manager.db = test_database
    manager.set_name = AsyncMock()
    manager.set_reminder_times = AsyncMock()
    manager.clear_reminders = AsyncMock()
    manager.set_bonus_available = AsyncMock()
    return manager


@pytest.fixture
def sample_user_data():
    """Возвращает тестовые данные пользователя."""
    return {
        "id": 123456789,
        "name": "Test User",
        "username": "test_user",
        "created_at": "2024-01-01T00:00:00+00:00",
        "last_request": "2024-01-01T12:00:00+00:00",
        "reminder_time": "09:00",
        "reminder_time_evening": "21:00",
        "bonus_available": True
    }


@pytest.fixture
def sample_card_data():
    """Возвращает тестовые данные карты."""
    return {
        "user_id": 123456789,
        "date": "2024-01-01",
        "card_number": 1,
        "user_request": "Тестовый запрос",
        "initial_resource": "😊 Хорошо",
        "final_resource": "😊 Хорошо",
        "recharge_method": "Прогулка",
        "created_at": "2024-01-01T12:00:00+00:00"
    }


@pytest.fixture
def sample_reflection_data():
    """Возвращает тестовые данные рефлексии."""
    return {
        "user_id": 123456789,
        "date": "2024-01-01",
        "good_moments": "Хороший день",
        "gratitude": "Благодарна за все",
        "hard_moments": "Немного устала",
        "ai_summary": "Позитивный день",
        "created_at": "2024-01-01T21:00:00+00:00"
    }


@pytest.fixture(autouse=True)
def mock_env_vars():
    """Мокает переменные окружения для тестов."""
    with patch.dict(os.environ, {
        'TELEGRAM_BOT_TOKEN': 'test_token_12345',
        'YANDEX_API_KEY': 'test_yandex_key',
        'YANDEX_FOLDER_ID': 'test_folder_id',
        'GROK_API_KEY': 'test_grok_key'
    }):
        yield


@pytest.fixture(autouse=True)
def mock_telegram_api():
    """Мокает вызовы к Telegram API."""
    with patch('aiogram.Bot') as mock_bot_class:
        mock_bot_instance = MagicMock()
        mock_bot_instance.send_message = AsyncMock()
        mock_bot_instance.get_chat_member = AsyncMock()
        mock_bot_class.return_value = mock_bot_instance
        yield mock_bot_instance


@pytest.fixture(autouse=True)
def mock_yandex_api():
    """Мокает вызовы к YandexGPT API."""
    with patch('httpx.AsyncClient.post') as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "alternatives": [{
                    "message": {
                        "text": "Тестовый ответ от YandexGPT"
                    }
                }]
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        yield mock_post 