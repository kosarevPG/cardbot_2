# -*- coding: utf-8 -*-
"""
Тесты для конфигурации и строковых констант.
"""

import pytest
import os
from unittest.mock import patch
from config import (
    TOKEN, CHANNEL_ID, BOT_LINK, TIMEZONE, ADMIN_ID,
    YANDEX_API_KEY, YANDEX_FOLDER_ID, YANDEX_GPT_URL,
    GROK_API_KEY, GROK_API_URL, NO_CARD_LIMIT_USERS,
    NO_LOGS_USERS, DATA_DIR
)
from strings import (
    UNIVERSE_ADVICE_LIST, START_NEW_USER_MESSAGE, START_EXISTING_USER_MESSAGE,
    RESOURCE_LEVELS, MAIN_MENU_CARD_OF_DAY, MAIN_MENU_EVENING_SUMMARY,
    MAIN_MENU_UNIVERSE_HINT, DEFAULT_NAME
)


class TestConfig:
    """Тесты для config.py."""

    def test_token_loading(self):
        """Тест загрузки токена из переменных окружения."""
        assert TOKEN == "test_token_12345"

    def test_yandex_config_loading(self):
        """Тест загрузки конфигурации YandexGPT."""
        assert YANDEX_API_KEY == "test_yandex_key"
        assert YANDEX_FOLDER_ID == "test_folder_id"
        assert YANDEX_GPT_URL == "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

    def test_grok_config_loading(self):
        """Тест загрузки конфигурации Grok."""
        assert GROK_API_KEY == "test_grok_key"
        assert GROK_API_URL == "https://api.x.ai/v1/chat/completions"

    def test_constants(self):
        """Тест констант."""
        assert CHANNEL_ID == "@TopPsyGame"
        assert BOT_LINK == "t.me/choose_a_card_bot"
        assert ADMIN_ID == 6682555021
        assert DATA_DIR == "/data"

    def test_user_lists(self):
        """Тест списков пользователей."""
        assert isinstance(NO_CARD_LIMIT_USERS, list)
        assert isinstance(NO_LOGS_USERS, list)
        assert 6682555021 in NO_CARD_LIMIT_USERS
        assert 6682555021 in NO_LOGS_USERS

    def test_timezone(self):
        """Тест настройки часового пояса."""
        assert TIMEZONE is not None
        assert str(TIMEZONE) == "Europe/Moscow"


class TestStrings:
    """Тесты для strings.py."""

    def test_universe_advice_list(self):
        """Тест списка советов Вселенной."""
        assert isinstance(UNIVERSE_ADVICE_LIST, list)
        assert len(UNIVERSE_ADVICE_LIST) > 0
        assert all(isinstance(advice, str) for advice in UNIVERSE_ADVICE_LIST)
        assert all("<b>💌" in advice for advice in UNIVERSE_ADVICE_LIST)

    def test_start_messages(self):
        """Тест сообщений для команды /start."""
        assert isinstance(START_NEW_USER_MESSAGE, str)
        assert isinstance(START_EXISTING_USER_MESSAGE, str)
        assert "Здравствуй" in START_NEW_USER_MESSAGE
        assert "{name}" in START_EXISTING_USER_MESSAGE

    def test_resource_levels(self):
        """Тест уровней ресурса."""
        assert isinstance(RESOURCE_LEVELS, dict)
        assert "resource_good" in RESOURCE_LEVELS
        assert "resource_medium" in RESOURCE_LEVELS
        assert "resource_low" in RESOURCE_LEVELS
        assert "😊 Хорошо" in RESOURCE_LEVELS.values()
        assert "😐 Средне" in RESOURCE_LEVELS.values()
        assert "😔 Низко" in RESOURCE_LEVELS.values()

    def test_main_menu_buttons(self):
        """Тест кнопок главного меню."""
        assert MAIN_MENU_CARD_OF_DAY == "✨ Карта дня"
        assert MAIN_MENU_EVENING_SUMMARY == "🌙 Итог дня"
        assert MAIN_MENU_UNIVERSE_HINT == "💌 Подсказка Вселенной"

    def test_default_name(self):
        """Тест значения по умолчанию для имени."""
        assert DEFAULT_NAME == "Друг"

    def test_string_formatting(self):
        """Тест форматирования строк."""
        # Тест форматирования сообщения с именем
        formatted_message = START_EXISTING_USER_MESSAGE.format(name="Анна")
        assert "Анна" in formatted_message
        assert "снова рад тебя видеть" in formatted_message

        # Тест форматирования сообщения без имени
        formatted_message_no_name = START_EXISTING_USER_MESSAGE.format(name="")
        assert "снова рад тебя видеть" in formatted_message_no_name

    def test_all_strings_are_strings(self):
        """Тест, что все импортированные константы являются строками."""
        string_constants = [
            START_NEW_USER_MESSAGE, START_EXISTING_USER_MESSAGE,
            MAIN_MENU_CARD_OF_DAY, MAIN_MENU_EVENING_SUMMARY,
            MAIN_MENU_UNIVERSE_HINT, DEFAULT_NAME
        ]
        
        for constant in string_constants:
            assert isinstance(constant, str), f"Константа {constant} не является строкой"

    def test_universe_advice_format(self):
        """Тест формата советов Вселенной."""
        for advice in UNIVERSE_ADVICE_LIST:
            # Проверяем, что каждый совет содержит HTML-теги
            assert "<b>" in advice
            assert "</b>" in advice
            # Проверяем, что каждый совет содержит эмодзи
            assert "💌" in advice
            # Проверяем длину совета
            assert len(advice) > 20, f"Совет слишком короткий: {advice}"


class TestConfigIntegration:
    """Интеграционные тесты конфигурации."""

    def test_config_with_missing_env_vars(self):
        """Тест поведения при отсутствии переменных окружения."""
        with patch.dict(os.environ, {}, clear=True):
            # Перезагружаем модуль config
            import importlib
            import config
            importlib.reload(config)
            
            # Проверяем, что токены стали None
            assert config.TOKEN is None
            assert config.YANDEX_API_KEY is None
            assert config.YANDEX_FOLDER_ID is None
            assert config.GROK_API_KEY is None

    def test_config_with_partial_env_vars(self):
        """Тест поведения при частично заданных переменных окружения."""
        with patch.dict(os.environ, {
            'TELEGRAM_BOT_TOKEN': 'partial_token',
            'YANDEX_API_KEY': 'partial_yandex_key'
        }):
            # Перезагружаем модуль config
            import importlib
            import config
            importlib.reload(config)
            
            assert config.TOKEN == 'partial_token'
            assert config.YANDEX_API_KEY == 'partial_yandex_key'
            assert config.YANDEX_FOLDER_ID is None
            assert config.GROK_API_KEY is None 