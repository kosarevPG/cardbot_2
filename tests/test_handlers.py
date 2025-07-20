# -*- coding: utf-8 -*-
"""
Тесты для обработчиков команд бота.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Импорты из проекта
from modules.user_management import UserState
from strings import (
    START_NEW_USER_MESSAGE, START_EXISTING_USER_MESSAGE, REFERRAL_BONUS_MESSAGE,
    REMIND_MESSAGE, REMIND_PURPOSE_TEXT, REMIND_INSTRUCTION_TEXT,
    MORNING_REMINDER_TEXT, MORNING_REMINDER_DISABLED,
    EVENING_REMINDER_TEXT, EVENING_REMINDER_DISABLED,
    REMIND_OFF_SUCCESS_MESSAGE, REMIND_OFF_ERROR_MESSAGE,
    SHARE_MESSAGE, NAME_CURRENT_MESSAGE, NAME_NEW_MESSAGE, NAME_INSTRUCTION,
    FEEDBACK_MESSAGE, BUTTON_SKIP, DEFAULT_NAME
)


class TestStartHandler:
    """Тесты для обработчика команды /start."""

    @pytest.mark.asyncio
    async def test_start_new_user(self, mock_message, mock_fsm_context, test_database, mock_logging_service, mock_user_manager):
        """Тест команды /start для нового пользователя."""
        # Настраиваем моки
        test_database.get_user.return_value = None  # Пользователь не существует
        
        # Импортируем функцию обработчика
        from main import make_start_handler
        start_handler = make_start_handler(test_database, mock_logging_service, mock_user_manager)
        
        # Вызываем обработчик
        await start_handler(mock_message, mock_fsm_context, None)
        
        # Проверяем, что отправлено правильное сообщение
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        assert START_NEW_USER_MESSAGE in str(call_args)
        
        # Проверяем, что создан пользователь
        test_database.create_user.assert_called_once()
        
        # Проверяем логирование
        mock_logging_service.log_action.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_existing_user(self, mock_message, mock_fsm_context, test_database, mock_logging_service, mock_user_manager):
        """Тест команды /start для существующего пользователя."""
        # Настраиваем моки
        existing_user = {
            "id": mock_message.from_user.id,
            "name": "Test User",
            "username": "test_user"
        }
        test_database.get_user.return_value = existing_user
        
        # Импортируем функцию обработчика
        from main import make_start_handler
        start_handler = make_start_handler(test_database, mock_logging_service, mock_user_manager)
        
        # Вызываем обработчик
        await start_handler(mock_message, mock_fsm_context, None)
        
        # Проверяем, что отправлено правильное сообщение
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        assert START_EXISTING_USER_MESSAGE.format(name="Test User") in str(call_args)

    @pytest.mark.asyncio
    async def test_start_with_referral(self, mock_message, mock_fsm_context, test_database, mock_logging_service, mock_user_manager, mock_bot):
        """Тест команды /start с реферальной ссылкой."""
        # Настраиваем моки
        test_database.get_user.return_value = None
        test_database.add_referral.return_value = True  # Реферал добавлен успешно
        
        referrer_data = {
            "id": 987654321,
            "name": "Referrer User",
            "bonus_available": False
        }
        test_database.get_user.side_effect = [None, referrer_data]  # Сначала новый пользователь, потом реферер
        
        # Настраиваем команду с реферальной ссылкой
        mock_message.text = "/start ref_987654321"
        
        # Импортируем функцию обработчика
        from main import make_start_handler
        start_handler = make_start_handler(test_database, mock_logging_service, mock_user_manager)
        
        # Создаем mock для CommandObject
        mock_command = MagicMock()
        mock_command.args = "ref_987654321"
        
        # Вызываем обработчик
        await start_handler(mock_message, mock_fsm_context, mock_command)
        
        # Проверяем, что реферал добавлен
        test_database.add_referral.assert_called_once_with(987654321, mock_message.from_user.id)
        
        # Проверяем, что отправлено сообщение рефереру
        mock_bot.send_message.assert_called_once()


class TestRemindHandler:
    """Тесты для обработчика команды /remind."""

    @pytest.mark.asyncio
    async def test_remind_handler(self, mock_message, mock_fsm_context, test_database, mock_logging_service, mock_user_manager):
        """Тест команды /remind."""
        # Настраиваем моки
        user_data = {
            "name": "Test User",
            "reminder_time": "09:00",
            "reminder_time_evening": "21:00"
        }
        test_database.get_user.return_value = user_data
        
        # Импортируем функцию обработчика
        from main import make_remind_handler
        remind_handler = make_remind_handler(test_database, mock_logging_service, mock_user_manager)
        
        # Вызываем обработчик
        await remind_handler(mock_message, mock_fsm_context)
        
        # Проверяем, что отправлено правильное сообщение
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        assert REMIND_PURPOSE_TEXT in str(call_args)
        assert MORNING_REMINDER_TEXT.format(time="09:00") in str(call_args)
        assert EVENING_REMINDER_TEXT.format(time="21:00") in str(call_args)

    @pytest.mark.asyncio
    async def test_remind_handler_no_reminders(self, mock_message, mock_fsm_context, test_database, mock_logging_service, mock_user_manager):
        """Тест команды /remind без установленных напоминаний."""
        # Настраиваем моки
        user_data = {
            "name": "Test User",
            "reminder_time": None,
            "reminder_time_evening": None
        }
        test_database.get_user.return_value = user_data
        
        # Импортируем функцию обработчика
        from main import make_remind_handler
        remind_handler = make_remind_handler(test_database, mock_logging_service, mock_user_manager)
        
        # Вызываем обработчик
        await remind_handler(mock_message, mock_fsm_context)
        
        # Проверяем, что отправлено правильное сообщение
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        assert MORNING_REMINDER_DISABLED in str(call_args)
        assert EVENING_REMINDER_DISABLED in str(call_args)


class TestRemindOffHandler:
    """Тесты для обработчика команды /remind_off."""

    @pytest.mark.asyncio
    async def test_remind_off_success(self, mock_message, mock_fsm_context, test_database, mock_logging_service, mock_user_manager):
        """Тест успешного отключения напоминаний."""
        # Настраиваем моки
        user_data = {"name": "Test User"}
        test_database.get_user.return_value = user_data
        
        # Импортируем функцию обработчика
        from main import make_remind_off_handler
        remind_off_handler = make_remind_off_handler(test_database, mock_logging_service, mock_user_manager)
        
        # Вызываем обработчик
        await remind_off_handler(mock_message, mock_fsm_context)
        
        # Проверяем, что напоминания отключены
        mock_user_manager.clear_reminders.assert_called_once_with(mock_message.from_user.id)
        
        # Проверяем сообщение
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        assert REMIND_OFF_SUCCESS_MESSAGE.format(name="Test User") in str(call_args)


class TestShareHandler:
    """Тесты для обработчика команды /share."""

    @pytest.mark.asyncio
    async def test_share_handler(self, mock_message, test_database, mock_logging_service):
        """Тест команды /share."""
        # Настраиваем моки
        user_data = {"name": "Test User"}
        test_database.get_user.return_value = user_data
        
        # Импортируем функцию обработчика
        from main import make_share_handler
        share_handler = make_share_handler(test_database, mock_logging_service)
        
        # Вызываем обработчик
        await share_handler(mock_message)
        
        # Проверяем, что отправлено правильное сообщение
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        assert SHARE_MESSAGE.format(name="Test User", ref_link="t.me/choose_a_card_bot?start=ref_123456789") in str(call_args)


class TestNameHandler:
    """Тесты для обработчика команды /name."""

    @pytest.mark.asyncio
    async def test_name_handler_with_name(self, mock_message, mock_fsm_context, test_database, mock_logging_service, mock_user_manager):
        """Тест команды /name с существующим именем."""
        # Настраиваем моки
        user_data = {"name": "Test User"}
        test_database.get_user.return_value = user_data
        
        # Импортируем функцию обработчика
        from main import make_name_handler
        name_handler = make_name_handler(test_database, mock_logging_service, mock_user_manager)
        
        # Вызываем обработчик
        await name_handler(mock_message, mock_fsm_context)
        
        # Проверяем, что отправлено правильное сообщение
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        assert NAME_CURRENT_MESSAGE.format(name="Test User") in str(call_args)
        assert NAME_INSTRUCTION in str(call_args)

    @pytest.mark.asyncio
    async def test_name_handler_without_name(self, mock_message, mock_fsm_context, test_database, mock_logging_service, mock_user_manager):
        """Тест команды /name без существующего имени."""
        # Настраиваем моки
        user_data = {"name": None}
        test_database.get_user.return_value = user_data
        
        # Импортируем функцию обработчика
        from main import make_name_handler
        name_handler = make_name_handler(test_database, mock_logging_service, mock_user_manager)
        
        # Вызываем обработчик
        await name_handler(mock_message, mock_fsm_context)
        
        # Проверяем, что отправлено правильное сообщение
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        assert NAME_NEW_MESSAGE in str(call_args)
        assert NAME_INSTRUCTION in str(call_args)


class TestFeedbackHandler:
    """Тесты для обработчика команды /feedback."""

    @pytest.mark.asyncio
    async def test_feedback_handler(self, mock_message, mock_fsm_context, test_database, mock_logging_service):
        """Тест команды /feedback."""
        # Настраиваем моки
        user_data = {"name": "Test User"}
        test_database.get_user.return_value = user_data
        
        # Импортируем функцию обработчика
        from main import make_feedback_handler
        feedback_handler = make_feedback_handler(test_database, mock_logging_service)
        
        # Вызываем обработчик
        await feedback_handler(mock_message, mock_fsm_context)
        
        # Проверяем, что отправлено правильное сообщение
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        assert FEEDBACK_MESSAGE.format(name="Test User") in str(call_args)
        
        # Проверяем, что установлено состояние
        mock_fsm_context.set_state.assert_called_once_with(UserState.waiting_for_feedback)


class TestProcessNameHandler:
    """Тесты для обработчика ввода имени."""

    @pytest.mark.asyncio
    async def test_process_name_success(self, mock_message, mock_fsm_context, test_database, mock_logging_service, mock_user_manager):
        """Тест успешного ввода имени."""
        # Настраиваем моки
        mock_message.text = "Новое Имя"
        
        # Импортируем функцию обработчика
        from main import make_process_name_handler
        process_name_handler = make_process_name_handler(test_database, mock_logging_service, mock_user_manager)
        
        # Вызываем обработчик
        await process_name_handler(mock_message, mock_fsm_context)
        
        # Проверяем, что имя установлено
        mock_user_manager.set_name.assert_called_once_with(mock_message.from_user.id, "Новое Имя")
        
        # Проверяем, что состояние очищено
        mock_fsm_context.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_name_empty(self, mock_message, mock_fsm_context, test_database, mock_logging_service, mock_user_manager):
        """Тест ввода пустого имени."""
        # Настраиваем моки
        mock_message.text = ""
        
        # Импортируем функцию обработчика
        from main import make_process_name_handler
        process_name_handler = make_process_name_handler(test_database, mock_logging_service, mock_user_manager)
        
        # Вызываем обработчик
        await process_name_handler(mock_message, mock_fsm_context)
        
        # Проверяем, что отправлено сообщение об ошибке
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        assert "Имя не может быть пустым" in str(call_args)


class TestProcessSkipNameHandler:
    """Тесты для обработчика пропуска ввода имени."""

    @pytest.mark.asyncio
    async def test_process_skip_name(self, mock_callback_query, mock_fsm_context, test_database, mock_logging_service, mock_user_manager):
        """Тест пропуска ввода имени."""
        # Импортируем функцию обработчика
        from main import make_process_skip_name_handler
        process_skip_name_handler = make_process_skip_name_handler(test_database, mock_logging_service, mock_user_manager)
        
        # Вызываем обработчик
        await process_skip_name_handler(mock_callback_query, mock_fsm_context)
        
        # Проверяем, что состояние очищено
        mock_fsm_context.clear.assert_called_once()
        
        # Проверяем, что отправлен ответ на callback
        mock_callback_query.answer.assert_called_once()


class TestProcessFeedbackHandler:
    """Тесты для обработчика ввода обратной связи."""

    @pytest.mark.asyncio
    async def test_process_feedback_success(self, mock_message, mock_fsm_context, test_database, mock_logging_service):
        """Тест успешного ввода обратной связи."""
        # Настраиваем моки
        mock_message.text = "Отличный бот! Спасибо!"
        
        # Импортируем функцию обработчика
        from main import make_process_feedback_handler
        process_feedback_handler = make_process_feedback_handler(test_database, mock_logging_service)
        
        # Вызываем обработчик
        await process_feedback_handler(mock_message, mock_fsm_context)
        
        # Проверяем, что обратная связь сохранена
        test_database.save_feedback.assert_called_once_with(
            mock_message.from_user.id,
            "Отличный бот! Спасибо!"
        )
        
        # Проверяем, что состояние очищено
        mock_fsm_context.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_feedback_empty(self, mock_message, mock_fsm_context, test_database, mock_logging_service):
        """Тест ввода пустой обратной связи."""
        # Настраиваем моки
        mock_message.text = ""
        
        # Импортируем функцию обработчика
        from main import make_process_feedback_handler
        process_feedback_handler = make_process_feedback_handler(test_database, mock_logging_service)
        
        # Вызываем обработчик
        await process_feedback_handler(mock_message, mock_fsm_context)
        
        # Проверяем, что отправлено сообщение об ошибке
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        assert "Обратная связь не может быть пустой" in str(call_args) 