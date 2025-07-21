# код/modules/quiz_handler.py

import logging
from aiogram import Bot, types
from aiogram.fsm.context import FSMContext

from .user_management import QuizState
from database.db import Database
from modules.logging_service import LoggingService

logger = logging.getLogger(__name__)

# --- Логика запуска и проведения опросника ---

async def start_mak_quiz(user_id: int, state: FSMContext, logger_service: LoggingService, bot: Bot):
    """Начинает опросник после завершения обучающего курса."""
    await logger_service.log_action(user_id, "quiz_started", {"quiz_id": "mak_tutorial_quiz"})
    
    await bot.send_message(user_id, "Отлично! Обучение завершено. А теперь небольшой опрос, чтобы закрепить знания и собрать обратную связь. Это займет 4-6 минут.")
    
    # --- Блок 1: Вопрос 1 (Правда/Миф) ---
    await state.set_state(QuizState.q1_truth_myth)
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Правда", callback_data="quiz_q1_true")],
        [types.InlineKeyboardButton(text="Миф", callback_data="quiz_q1_false")]
    ])
    await bot.send_message(user_id, "<b>Вопрос 1/4:</b>\nМАК — это инструмент для работы с бессознательным, а не гадание.", reply_markup=keyboard, parse_mode="HTML")

async def process_q1_callback(callback: types.CallbackQuery, state: FSMContext, db: Database):
    """Обрабатывает ответ на Вопрос 1 и задает Вопрос 2."""
    answer = callback.data
    is_correct = (answer == "quiz_q1_true")
    
    # Сохраняем результат
    # db.save_quiz_answer(...) # Здесь будет логика сохранения в БД
    
    await state.update_data(q1_score=1 if is_correct else 0)
    await callback.message.edit_text(f"<b>Вопрос 1/4:</b> ...\nВаш ответ принят! Правильный ответ: <b>Правда</b>.", parse_mode="HTML")
    
    # --- Блок 1: Вопрос 2 (Викторина) ---
    await state.set_state(QuizState.q2_quiz)
    await callback.message.answer_poll(
        question="Вопрос 2/4: Что из этого НЕ является ключевым условием эффективной сессии с МАК?",
        options=[
            "Безопасное пространство",
            "Четкий ответ от специалиста",
            "Открытый вопрос",
            "Доверие процессу"
        ],
        type='quiz',
        correct_option_id=1,  # "Четкий ответ от специалиста" - неправильное условие
        is_anonymous=False,
        explanation="Основа МАК — самостоятельные инсайты клиента, а не готовые ответы от специалиста."
    )
    # После квиза нужна кнопка для продолжения
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Продолжить", callback_data="quiz_continue_to_q3")]
    ])
    await callback.message.answer("Когда будете готовы, нажмите 'Продолжить'.", reply_markup=keyboard)


async def process_q2_continue_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает кнопку 'Продолжить' после квиза и задает Вопрос 3."""
    # --- Блок 2: Саморефлексия ---
    await state.set_state(QuizState.q3_self_reflection)
    likert_kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="1", callback_data="quiz_q3_1"),
            types.InlineKeyboardButton(text="2", callback_data="quiz_q3_2"),
            types.InlineKeyboardButton(text="3", callback_data="quiz_q3_3"),
            types.InlineKeyboardButton(text="4", callback_data="quiz_q3_4"),
            types.InlineKeyboardButton(text="5", callback_data="quiz_q3_5"),
        ]
    ])
    await callback.message.edit_text(
        "<b>Блок саморефлексии (Вопрос 3/4):</b>\nОцените по шкале от 1 (совсем нет) до 5 (полностью да):\n\n"
        "<i>«После курса я лучше понимаю, чем МАК отличается от гадания».</i>",
        reply_markup=likert_kb,
        parse_mode="HTML"
    )

async def process_q3_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает ответ на Вопрос 3 и задает Вопрос 4."""
    # db.save_quiz_answer(...) # Сохраняем ответ
    
    await callback.message.edit_text(f"<b>Блок саморефлексии (Вопрос 3/4):</b> ...\nВаш ответ принят!", parse_mode="HTML")
    
    # --- Блок 3: Обратная связь ---
    await state.set_state(QuizState.q4_feedback)
    await callback.message.answer("<b>Вопрос 4/4:</b>\nЧто оказалось самым полезным в этом коротком обучении? (Напишите 1-2 предложения)")


async def process_q4_text(message: types.Message, state: FSMContext, db: Database, logger_service: LoggingService):
    """Обрабатывает текстовый фидбек и завершает опрос."""
    user_id = message.from_user.id
    feedback_text = message.text
    # db.save_quiz_answer(...) # Сохраняем
    await logger_service.log_action(user_id, "quiz_feedback_provided", {"quiz_id": "mak_tutorial_quiz", "feedback": feedback_text})
    
    # Подсчет очков (пока простой)
    data = await state.get_data()
    score = data.get("q1_score", 0)
    
    await message.answer(f"Спасибо за ваши ответы! ❤️\n\nВы отлично справились с блоком на знание.\nВаш фидбек поможет сделать обучение еще лучше!\n\nОпрос завершен.", parse_mode="HTML")
    
    await state.clear() 