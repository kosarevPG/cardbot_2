# код/evening_reflection.py

import logging
from datetime import datetime
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram import F, Router # Используем Router для удобства

# Локальные импорты
from modules.user_management import UserState
from database.db import Database
from modules.logging_service import LoggingService
from config import TIMEZONE
# --- НОВЫЙ ИМПОРТ ---
from modules.ai_service import get_reflection_summary # Импортируем новую функцию
# --- КОНЕЦ НОВОГО ИМПОРТА ---
from modules.card_of_the_day import get_main_menu

logger = logging.getLogger(__name__)

# Создаем Router для этого модуля
# (Оставляем его, если он используется для других обработчиков, например, callback_query,
#  или если планируется его использовать в будущем. Если нет - можно удалить)
reflection_router = Router()

# Импорт строковых констант
from strings import (
    EVENING_REFLECTION_INTRO, EVENING_REFLECTION_GOOD_MOMENTS, EVENING_REFLECTION_GRATITUDE,
    EVENING_REFLECTION_HARD_MOMENTS, EVENING_REFLECTION_CONCLUSION, EVENING_REFLECTION_INPUT_ERROR,
    EVENING_REFLECTION_AI_SUMMARY_PREFIX, EVENING_REFLECTION_AI_SUMMARY_FAIL, EVENING_REFLECTION_SAVE_ERROR
)

# --- Хендлеры ---

# Эта функция будет вызываться из main.py, зарегистрированная напрямую на dp
async def start_evening_reflection(message: types.Message, state: FSMContext, db: Database, logger_service: LoggingService):
    """Начало флоу 'Итог дня'."""
    user_id = message.from_user.id
    await logger_service.log_action(user_id, "evening_reflection_started")
    await message.answer(EVENING_REFLECTION_INTRO)
    await message.answer(EVENING_REFLECTION_GOOD_MOMENTS)
    await state.set_state(UserState.waiting_for_good_moments)

# УБРАН ДЕКОРАТОР @reflection_router.message(...)
# Эта функция будет вызываться из main.py, зарегистрированная напрямую на dp
async def process_good_moments(message: types.Message, state: FSMContext, db: Database, logger_service: LoggingService):
    """Обработка ответа на вопрос о хороших моментах."""
    user_id = message.from_user.id
    answer = message.text.strip()
    if not answer:
        await message.reply(MSG_INPUT_ERROR)
        return

    await state.update_data(good_moments=answer)
    await logger_service.log_action(user_id, "evening_reflection_good_provided", {"length": len(answer)})
    await message.answer(EVENING_REFLECTION_GRATITUDE)
    await state.set_state(UserState.waiting_for_gratitude)

# УБРАН ДЕКОРАТОР @reflection_router.message(...)
# Эта функция будет вызываться из main.py, зарегистрированная напрямую на dp
async def process_gratitude(message: types.Message, state: FSMContext, db: Database, logger_service: LoggingService):
    """Обработка ответа на вопрос о благодарности."""
    user_id = message.from_user.id
    answer = message.text.strip()
    if not answer:
        await message.reply(EVENING_REFLECTION_INPUT_ERROR)
        return

    await state.update_data(gratitude=answer)
    await logger_service.log_action(user_id, "evening_reflection_gratitude_provided", {"length": len(answer)})
    await message.answer(EVENING_REFLECTION_HARD_MOMENTS)
    await state.set_state(UserState.waiting_for_hard_moments)

# УБРАН ДЕКОРАТОР @reflection_router.message(...)
# Эта функция будет вызываться из main.py, зарегистрированная напрямую на dp
async def process_hard_moments(message: types.Message, state: FSMContext, db: Database, logger_service: LoggingService):
    """Обработка ответа на вопрос о непростых моментах, генерация AI-резюме и завершение."""
    user_id = message.from_user.id
    hard_moments_answer = message.text.strip()
    if not hard_moments_answer:
        await message.reply(EVENING_REFLECTION_INPUT_ERROR)
        return

    await state.update_data(hard_moments=hard_moments_answer)
    await logger_service.log_action(user_id, "evening_reflection_hard_provided", {"length": len(hard_moments_answer)})

    # --- НАЧАЛО ИНТЕГРАЦИИ AI ---
    data = await state.get_data()
    ai_summary_text = None # Инициализируем переменную для резюме
    try:
        # Показываем "печатает..." пока генерируется резюме
        await message.bot.send_chat_action(user_id, 'typing') # <--- Индикатор "печатает..."
        ai_summary_text = await get_reflection_summary(user_id, data, db)

        if ai_summary_text:
            await message.answer(f"{EVENING_REFLECTION_AI_SUMMARY_PREFIX}<i>{ai_summary_text}</i>", parse_mode="HTML") # Добавлен parse_mode HTML
            await logger_service.log_action(user_id, "evening_reflection_summary_sent")
        else:
            # Если AI вернул None или пустую строку (из-за непредвиденной ошибки в ai_service)
            await message.answer(EVENING_REFLECTION_AI_SUMMARY_FAIL)
            await logger_service.log_action(user_id, "evening_reflection_summary_failed", {"reason": "AI service returned None"})

    except Exception as ai_err:
        logger.error(f"Error during AI reflection summary generation for user {user_id}: {ai_err}", exc_info=True)
        await message.answer(EVENING_REFLECTION_AI_SUMMARY_FAIL) # Сообщаем пользователю об ошибке
        await logger_service.log_action(user_id, "evening_reflection_summary_failed", {"reason": str(ai_err)})
        ai_summary_text = None # Убедимся, что в БД не запишется ошибка
    # --- КОНЕЦ ИНТЕГРАЦИИ AI ---

    # Сохранение данных в БД (включая ai_summary_text, который может быть None)
    good_moments = data.get("good_moments")
    gratitude = data.get("gratitude")

    try:
        today_str = datetime.now(TIMEZONE).strftime('%Y-%m-%d')
        created_at_iso = datetime.now(TIMEZONE).isoformat()
        # --- ИСПРАВЛЕНИЕ: УБИРАЕМ await ПЕРЕД db.save_evening_reflection ---
        db.save_evening_reflection(
            user_id=user_id,
            date=today_str,
            good_moments=good_moments,
            gratitude=gratitude,
            hard_moments=hard_moments_answer,
            created_at=created_at_iso,
            ai_summary=ai_summary_text # <--- ПЕРЕДАЕМ РЕЗЮМЕ
        )
        # Лог об успешном сохранении будет внутри db.save_evening_reflection
        await logger_service.log_action(user_id, "evening_reflection_saved_to_db") # Оставляем этот общий лог
    except Exception as db_err:
        logger.error(f"Failed to save evening reflection for user {user_id}: {db_err}", exc_info=True)
        await message.answer(EVENING_REFLECTION_SAVE_ERROR)
        # Важно: очищаем состояние, даже если не сохранилось в БД, чтобы не зацикливаться
        await state.clear()
        return # Выходим, не показывая стандартное завершение

    # Завершение (отправка стандартного сообщения и меню)
    await message.answer(EVENING_REFLECTION_CONCLUSION, reply_markup=await get_main_menu(user_id, db))
    await state.clear() # Очищаем состояние
