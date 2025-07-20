# код/card_of_the_day.py

import random
import os
from aiogram import types
from aiogram.fsm.context import FSMContext
from config import TIMEZONE, NO_CARD_LIMIT_USERS, DATA_DIR, pytz # Убедимся, что pytz импортирован
# Импортируем функции из ai_service
from .ai_service import (
    get_grok_question, get_grok_summary, build_user_profile,
    get_grok_supportive_message
)
from datetime import datetime, date # Добавили date
from modules.user_management import UserState
from database.db import Database
import logging

logger = logging.getLogger(__name__)

# Словарь для маппинга callback -> emoji/text
RESOURCE_LEVELS = {
    "resource_good": "😊 Хорошо",
    "resource_medium": "😐 Средне",
    "resource_low": "😔 Низко",
}
# Путь к папке с картами
CARDS_DIR = os.path.join(DATA_DIR, "cards") if DATA_DIR != "/data" else "cards"
if not CARDS_DIR.startswith("/data") and not os.path.exists(CARDS_DIR):
     os.makedirs(CARDS_DIR, exist_ok=True)
     logger.warning(f"Cards directory '{CARDS_DIR}' did not exist and was created. Make sure card images are present.")


# --- Основная клавиатура (ИЗМЕНЕНО) ---
async def get_main_menu(user_id, db: Database):
    """Возвращает основную клавиатуру меню. (ИЗМЕНЕНО)"""
    keyboard = [
        [types.KeyboardButton(text="✨ Карта дня")],
        [types.KeyboardButton(text="🌙 Итог дня")]
    ]
    try:
        user_data = db.get_user(user_id)
        # --- ИЗМЕНЕНИЕ: Добавляем кнопку в конец, если бонус доступен ---
        if user_data and user_data.get("bonus_available"):
            # Используем append вместо insert(1, ...)
            keyboard.append([types.KeyboardButton(text="💌 Подсказка Вселенной")])
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---
    except Exception as e:
        logger.error(f"Error getting user data for main menu (user {user_id}): {e}", exc_info=True)
    # Используем persistent=True для постоянного отображения
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, persistent=True)


# ================================
# === НОВЫЙ СЦЕНАРИЙ КАРТЫ ДНЯ ===
# ================================

# --- Шаг 0: Начало флоу ---
async def handle_card_request(message: types.Message, state: FSMContext, db: Database, logger_service):
    """
    СТАРТОВАЯ ТОЧКА сценария 'Карта дня'.
    Проверяет доступность карты и запускает замер ресурса.
    """
    user_id = message.from_user.id
    user_data = db.get_user(user_id) or {}
    name = user_data.get("name") or ""
    name = name.strip() if isinstance(name, str) else ""
    now = datetime.now(TIMEZONE)
    today = now.date()

    logger.info(f"User {user_id}: Checking card availability for {today}")
    card_available = db.is_card_available(user_id, today)
    logger.info(f"User {user_id}: Card available? {card_available}")

    # *** Обратите внимание на эту логику - если пользователь в исключениях, он все равно пойдет дальше ***
    if user_id not in NO_CARD_LIMIT_USERS and not card_available:
        last_req_time_str = "неизвестно"
        if user_data and isinstance(user_data.get('last_request'), datetime):
            try:
                # Попытка сделать aware, если не aware, или просто конвертировать
                last_req_dt = user_data['last_request']
                if last_req_dt.tzinfo is None and pytz:
                    last_req_dt_local = TIMEZONE.localize(last_req_dt).astimezone(TIMEZONE)
                elif last_req_dt.tzinfo:
                    last_req_dt_local = last_req_dt.astimezone(TIMEZONE)
                else: # Если pytz нет или уже aware без него
                    last_req_dt_local = last_req_dt # Используем как есть
                last_req_time_str = last_req_dt_local.strftime('%H:%M %d.%m.%Y')
            except Exception as e:
                logger.error(f"Error formatting last_request time for user {user_id}: {e}")
                last_req_time_str = "ошибка времени"
        text = (f"{name}, ты уже вытянула карту сегодня (в {last_req_time_str} МСК)! Новая будет доступна завтра. ✨" if name else f"Ты уже вытянула карту сегодня (в {last_req_time_str} МСК)! Новая будет доступна завтра. ✨")
        logger.info(f"User {user_id}: Sending 'already drawn' message.")
        await message.answer(text, reply_markup=await get_main_menu(user_id, db))
        await state.clear()
        return

    # *** Эта строка может быть немного запутывающей, если card_available == False, но пользователь в исключениях ***
    logger.info(f"User {user_id}: Card available, starting initial resource check.")
    await logger_service.log_action(user_id, "card_flow_started", {"trigger": "button"})
    await ask_initial_resource(message, state, db, logger_service) # Переход к Шагу 1

# --- Шаг 1: Замер начального ресурса ---
async def ask_initial_resource(message: types.Message, state: FSMContext, db: Database, logger_service):
    """Шаг 1: Задает вопрос о начальном ресурсном состоянии."""
    user_id = message.from_user.id
    user_data = db.get_user(user_id) or {}
    name = user_data.get("name") or ""
    name = name.strip() if isinstance(name, str) else ""
    text = f"{name}, привет! ✨ Прежде чем мы начнем, как ты сейчас себя чувствуешь? Оцени свой уровень внутреннего ресурса:" if name else "Привет! ✨ Прежде чем мы начнем, как ты сейчас себя чувствуешь? Оцени свой уровень внутреннего ресурса:"
    buttons = [ types.InlineKeyboardButton(text=label.split()[0], callback_data=key) for key, label in RESOURCE_LEVELS.items() ]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[buttons])
    await message.answer(text, reply_markup=keyboard)
    await state.set_state(UserState.waiting_for_initial_resource)

# --- Обработка Шага 1 ---
async def process_initial_resource_callback(callback: types.CallbackQuery, state: FSMContext, db: Database, logger_service):
    """Шаг 1.5: Обрабатывает выбор ресурса, сохраняет его и переходит к выбору типа запроса."""
    user_id = callback.from_user.id
    resource_choice_key = callback.data
    resource_choice_label = RESOURCE_LEVELS.get(resource_choice_key, "Неизвестно")
    await state.update_data(initial_resource=resource_choice_label)
    await logger_service.log_action(user_id, "initial_resource_selected", {"resource": resource_choice_label})
    await callback.answer(f"Понял, твое состояние: {resource_choice_label.split()[0]}")
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e: logger.warning(f"Could not edit message reply markup (initial resource) for user {user_id}: {e}")
    await ask_request_type_choice(callback, state, db, logger_service) # Переход к Шагу 2

# --- Шаг 2: Выбор типа запроса ---
async def ask_request_type_choice(event: types.Message | types.CallbackQuery, state: FSMContext, db: Database, logger_service):
    """Шаг 2: Спрашивает, как пользователь хочет сформулировать запрос."""
    if isinstance(event, types.CallbackQuery):
        user_id = event.from_user.id; message = event.message
    else:
        user_id = event.from_user.id; message = event
    user_data = db.get_user(user_id) or {}
    name = user_data.get("name") or ""; name = name.strip() if isinstance(name, str) else ""
    text = (f"{name}, теперь подумай о своем запросе или теме дня.\n" if name else "Теперь подумай о своем запросе или теме дня.\n") + ("Как тебе удобнее?\n\n1️⃣ Сформулировать запрос <b>в уме</b>?\n2️⃣ <b>Написать</b> запрос прямо здесь в чат?\n\n<i>(Если напишешь, я смогу задать более точные вопросы к твоим ассоциациям ✨).</i>")
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[[ types.InlineKeyboardButton(text="1️⃣ В уме", callback_data="request_type_mental"), types.InlineKeyboardButton(text="2️⃣ Написать", callback_data="request_type_typed"), ]])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(UserState.waiting_for_request_type_choice)

# --- Обработка Шага 2 ---
async def process_request_type_callback(callback: types.CallbackQuery, state: FSMContext, db: Database, logger_service):
    """Шаг 2.5: Обрабатывает выбор типа запроса."""
    user_id = callback.from_user.id # <<< ID пользователя из колбэка
    request_type = callback.data
    choice_text = "В уме" if request_type == "request_type_mental" else "Написать"
    await state.update_data(request_type=request_type)
    await logger_service.log_action(user_id, "request_type_chosen", {"choice": choice_text})
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e: logger.warning(f"Could not edit message reply markup (request type) for user {user_id}: {e}")

    if request_type == "request_type_mental":
        await callback.answer("Хорошо, держи запрос в голове.")
        await callback.message.answer("Понял. Сейчас вытяну для тебя карту...")
        # Передаем user_id явно
        await draw_card_direct(callback.message, state, db, logger_service, user_id=user_id) # Переход к Шагу 3b
    elif request_type == "request_type_typed":
        await callback.answer("Отлично, жду твой запрос.")
        await callback.message.answer("Напиши, пожалуйста, свой запрос к карте (1-2 предложения):")
        await state.set_state(UserState.waiting_for_request_text_input) # Переход к Шагу 3a

# --- Шаг 3: Обработка текстового запроса ---
async def process_request_text(message: types.Message, state: FSMContext, db: Database, logger_service):
    """Шаг 3а: Получает текстовый запрос пользователя и тянет карту."""
    user_id = message.from_user.id # <<< ID пользователя из его сообщения
    request_text = message.text.strip()
    if not request_text: await message.answer("Запрос не может быть пустым..."); return
    if len(request_text) < 5: await message.answer("Пожалуйста, сформулируй запрос чуть подробнее..."); return
    await state.update_data(user_request=request_text)
    await logger_service.log_action(user_id, "request_text_provided", {"request": request_text})
    await message.answer("Спасибо! ✨ Сейчас вытяну карту для твоего запроса...")
    # Передаем user_id явно
    await draw_card_direct(message, state, db, logger_service, user_id=user_id) # Переход к Шагу 3b

# --- Функция вытягивания карты (ИЗМЕНЕНА) ---
async def draw_card_direct(message: types.Message, state: FSMContext, db: Database, logger_service, user_id: int):
    """
    Шаг 3b / Завершение Шага 3а:
    Вытягивает карту, отправляет ее и первый вопрос об ассоциациях.
    Устанавливает состояние waiting_for_initial_response.
    Использует переданный user_id.
    """
    # Используем переданный user_id
    user_data_fsm = await state.get_data()
    user_request = user_data_fsm.get("user_request", "")
    user_db_data = db.get_user(user_id) or {} # Получаем данные по правильному ID
    name = user_db_data.get("name") or ""
    name = name.strip() if isinstance(name, str) else ""
    now_iso = datetime.now(TIMEZONE).isoformat()

    try:
         # Обновляем время последнего запроса для правильного ID
         db.update_user(user_id, {"last_request": now_iso})
    except Exception as e:
         logger.error(f"Failed to update last_request time for user {user_id}: {e}", exc_info=True)

    card_number = None
    try:
        used_cards = db.get_user_cards(user_id)
        # Убедимся, что папка существует перед чтением
        if not os.path.isdir(CARDS_DIR):
             logger.error(f"Cards directory not found or not a directory: {CARDS_DIR}")
             await message.answer("Не могу найти папку с картами..."); await state.clear(); return

        all_card_files = [f for f in os.listdir(CARDS_DIR) if f.startswith("card_") and f.endswith(".jpg")]
        if not all_card_files:
            logger.error(f"No card images found in {CARDS_DIR}.")
            await message.answer("В папке нет изображений карт..."); await state.clear(); return

        all_cards = []
        for fname in all_card_files:
             try:
                 num = int(fname.replace("card_", "").replace(".jpg", ""))
                 all_cards.append(num)
             except ValueError:
                 logger.warning(f"Could not parse card number from filename: {fname}")
                 continue

        if not all_cards:
            logger.error(f"Could not parse any valid card numbers from filenames in {CARDS_DIR}.")
            await message.answer("Проблема с именами файлов карт..."); await state.clear(); return

        available_cards = [c for c in all_cards if c not in used_cards]
        if not available_cards:
            logger.info(f"Card deck reset for user {user_id} as all cards were used.")
            db.reset_user_cards(user_id)
            available_cards = all_cards.copy() # Сбрасываем до полного списка

        # Доп. проверка на случай, если даже после сброса карт нет (маловероятно)
        if not available_cards:
             logger.error(f"No available cards found even after potential reset for user {user_id}.")
             await message.answer("Не могу найти доступную карту..."); await state.clear(); return

        card_number = random.choice(available_cards)
        db.add_user_card(user_id, card_number) # Добавляем карту в использованные
        await state.update_data(card_number=card_number)

    except Exception as card_logic_err:
        logger.error(f"Error during card selection logic for user {user_id}: {card_logic_err}", exc_info=True)
        await message.answer("Произошла ошибка при выборе карты...")
        await state.clear()
        return # Выходим, если карту выбрать не удалось

    # Отправка карты и вопроса (если номер карты успешно определен)
    card_path = os.path.join(CARDS_DIR, f"card_{card_number}.jpg")
    if not os.path.exists(card_path):
        logger.error(f"Card image file not found: {card_path} after selecting number {card_number} for user {user_id}.")
        await message.answer("Изображение для выбранной карты потерялось...")
        await state.clear()
        return

    try:
        # Отправляем карту
        await message.bot.send_chat_action(message.chat.id, 'upload_photo')
        await message.answer_photo(types.FSInputFile(card_path), protect_content=True)
        await logger_service.log_action(user_id, "card_drawn", {"card_number": card_number, "request_provided": bool(user_request)}) # Лог для правильного user_id

        # Формулируем вопрос
        if user_request:
            text = (f"{name}, вот карта для твоего запроса:\n<i>«{user_request}»</i>\n\nРассмотри ее внимательно. Какие <b>первые чувства, образы, мысли или воспоминания</b> приходят? Как это может быть связано с твоим запросом?"
                    if name
                    else f"Вот карта для твоего запроса:\n<i>«{user_request}»</i>\n\nРассмотри ее внимательно. Какие <b>первые чувства, образы, мысли или воспоминания</b> приходят? Как это может быть связано с твоим запросом?")
        else:
            text = (f"{name}, вот твоя карта дня.\n\nВзгляни на нее. Какие <b>первые чувства, образы, мысли или воспоминания</b> приходят? Как это может быть связано с твоим сегодняшним состоянием?"
                    if name
                    else f"Вот твоя карта дня.\n\nВзгляни на нее. Какие <b>первые чувства, образы, мысли или воспоминания</b> приходят? Как это может быть связано с твоим сегодняшним состоянием?")

        # Отправляем вопрос и устанавливаем состояние
        await message.answer(text, parse_mode="HTML")
        await state.set_state(UserState.waiting_for_initial_response) # Переход к Шагу 4

    except Exception as e:
        logger.error(f"Failed to send card photo or initial question to user {user_id}: {e}", exc_info=True)
        await message.answer("Ой, не получилось отправить карту или вопрос...")
        await state.clear()


# --- Шаг 4: Обработка первой ассоциации ---
async def process_initial_response(message: types.Message, state: FSMContext, db: Database, logger_service):
    """Шаг 4.5: Получает первую ассоциацию, сохраняет ее и предлагает выбор: исследовать дальше."""
    user_id = message.from_user.id
    initial_response_text = message.text.strip()
    if not initial_response_text: await message.answer("Кажется, ты ничего не написала..."); return
    if len(initial_response_text) < 3: await message.answer("Пожалуйста, опиши ассоциации чуть подробнее..."); return
    data = await state.get_data()
    card_number = data.get("card_number", "N/A")
    user_request = data.get("user_request", "")
    await state.update_data(initial_response=initial_response_text)
    await logger_service.log_action(user_id, "initial_response_provided", {"card_number": card_number, "request": user_request, "response": initial_response_text})
    await ask_exploration_choice(message, state, db, logger_service) # Переход к Шагу 5

# --- Шаг 5: Выбор - исследовать дальше? ---
async def ask_exploration_choice(message: types.Message, state: FSMContext, db: Database, logger_service):
    """Шаг 5: Спрашивает, хочет ли пользователь исследовать ассоциации дальше с помощью Grok."""
    user_id = message.from_user.id
    user_data = db.get_user(user_id) or {}
    name = user_data.get("name") or ""
    name = name.strip() if isinstance(name, str) else ""
    text = (f"{name}, спасибо, что поделилась! Хочешь поисследовать эти ассоциации глубже с помощью нескольких вопросов от меня (это займет еще 5-7 минут)?" if name else "Спасибо, что поделилась! Хочешь поисследовать эти ассоциации глубже с помощью нескольких вопросов от меня (это займет еще 5-7 минут)?")
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="✅ Да, давай исследуем", callback_data="explore_yes")], [types.InlineKeyboardButton(text="❌ Нет, на сегодня хватит", callback_data="explore_no")]])
    await message.answer(text, reply_markup=keyboard)
    await state.set_state(UserState.waiting_for_exploration_choice)

# --- Обработка Шага 5 (ИСПРАВЛЕНО) ---
async def process_exploration_choice_callback(callback: types.CallbackQuery, state: FSMContext, db: Database, logger_service):
    """Шаг 5.5: Обрабатывает выбор об исследовании. (ИСПРАВЛЕНО)"""
    user_id = callback.from_user.id # <<< Получаем ID пользователя из колбэка
    choice = callback.data
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        logger.warning(f"Could not edit message reply markup (exploration choice) for user {user_id}: {e}")

    if choice == "explore_yes":
        await callback.answer("Отлично! Задаю первый вопрос...")
        await logger_service.log_action(user_id, "exploration_chosen", {"choice": "yes"})
        # Передаем user_id явно в ask_grok_question
        await ask_grok_question(callback.message, state, db, logger_service, step=1, user_id=user_id) # Переход к Шагу 6
    elif choice == "explore_no":
        await callback.answer("Хорошо, завершаем работу с картой.")
        await logger_service.log_action(user_id, "exploration_chosen", {"choice": "no"})
        # --- ИСПРАВЛЕНИЕ 1 и 2 ---
        # Передаем user_id явно в обе функции
        await generate_and_send_summary(user_id=user_id, message=callback.message, state=state, db=db, logger_service=logger_service) # <== Передали user_id
        await finish_interaction_flow(user_id=user_id, message=callback.message, state=state, db=db, logger_service=logger_service) # <== Передали user_id
        # --- КОНЕЦ ИСПРАВЛЕНИЯ ---


# --- Шаг 6: Цикл вопросов Grok (ИЗМЕНЕНА сигнатура) ---
async def ask_grok_question(message: types.Message, state: FSMContext, db: Database, logger_service, step: int, user_id: int):
    """Запрашивает и отправляет вопрос от Grok для шага step."""
    # Используем переданный user_id
    data = await state.get_data()
    user_request = data.get("user_request", "")
    initial_response = data.get("initial_response", "")
    # Собираем контекст предыдущих ответов
    previous_responses_context = { "initial_response": initial_response }
    if step > 1:
        previous_responses_context["grok_question_1"] = data.get("grok_question_1")
        previous_responses_context["first_grok_response"] = data.get("first_grok_response")
    if step > 2:
        previous_responses_context["grok_question_2"] = data.get("grok_question_2")
        previous_responses_context["second_grok_response"] = data.get("second_grok_response")

    # Определяем текущий ответ пользователя для запроса к Grok
    if step == 1: current_user_response = initial_response
    elif step == 2: current_user_response = data.get("first_grok_response", "")
    elif step == 3: current_user_response = data.get("second_grok_response", "")
    else:
        logger.error(f"Invalid step number {step} for Grok question for user {user_id}.")
        await message.answer("Произошла внутренняя ошибка шага...")
        await state.clear()
        return

    if not current_user_response:
        logger.error(f"Missing user response data for step {step} for user {user_id}.")
        await message.answer("Не могу найти предыдущий ответ для вопроса...")
        await state.clear()
        return

    try:
        await message.bot.send_chat_action(user_id, 'typing') # Используем правильный ID для chat_action
    except Exception as e:
        logger.error(f"Failed send_chat_action (typing) to user {user_id} in ask_grok_question: {e}")

    grok_question = await get_grok_question(
        user_id=user_id, # Передаем правильный ID в AI сервис
        user_request=user_request,
        user_response=current_user_response,
        feedback_type="exploration", # Уточнить, используется ли
        step=step,
        previous_responses=previous_responses_context,
        db=db
    )
    await state.update_data({f"grok_question_{step}": grok_question})
    await logger_service.log_action(user_id, "grok_question_asked", {"step": step, "question": grok_question}) # Лог с правильным ID

    try:
        await message.answer(grok_question) # Отправляем в чат пользователя
    except Exception as e:
        logger.error(f"Failed to send Grok question (step {step}) to user {user_id}: {e}", exc_info=True)
        await message.answer("Не удалось отправить вопрос...")
        await state.clear()
        return

    # Устанавливаем следующее состояние
    next_state = None
    if step == 1: next_state = UserState.waiting_for_first_grok_response
    elif step == 2: next_state = UserState.waiting_for_second_grok_response
    elif step == 3: next_state = UserState.waiting_for_third_grok_response

    if next_state:
        await state.set_state(next_state)
    else:
        # Это не должно произойти, если step валиден (1, 2, 3)
        logger.error(f"Invalid step {step} when trying to set next state for user {user_id}.")
        await state.clear()

# --- Обработка ответов на вопросы Grok ---
async def process_first_grok_response(message: types.Message, state: FSMContext, db: Database, logger_service):
    """Шаг 6a: Обрабатывает ответ на ПЕРВЫЙ вопрос Grok и задает второй."""
    user_id = message.from_user.id # <<< ID пользователя из его сообщения
    first_response = message.text.strip()
    if not first_response or len(first_response) < 2: await message.answer("Пожалуйста, попробуй ответить чуть подробнее."); return

    data = await state.get_data()
    first_grok_question = data.get("grok_question_1", "N/A")
    card_number = data.get("card_number", "N/A")
    user_request = data.get("user_request", "")

    await state.update_data(first_grok_response=first_response)
    await logger_service.log_action(user_id, "grok_response_provided", {"step": 1, "question": first_grok_question, "response": first_response, "card": card_number, "request": user_request})
    await ask_grok_question(message, state, db, logger_service, step=2, user_id=user_id) # Передаем user_id

async def process_second_grok_response(message: types.Message, state: FSMContext, db: Database, logger_service):
    """Шаг 6b: Обрабатывает ответ на ВТОРОЙ вопрос Grok и задает третий."""
    user_id = message.from_user.id # <<< ID пользователя из его сообщения
    second_response = message.text.strip()
    if not second_response or len(second_response) < 2: await message.answer("Пожалуйста, попробуй ответить чуть подробнее."); return

    data = await state.get_data()
    second_grok_question = data.get("grok_question_2", "N/A")
    card_number = data.get("card_number", "N/A")
    user_request = data.get("user_request", "")

    await state.update_data(second_grok_response=second_response)
    await logger_service.log_action(user_id, "grok_response_provided", {"step": 2, "question": second_grok_question, "response": second_response, "card": card_number, "request": user_request})
    await ask_grok_question(message, state, db, logger_service, step=3, user_id=user_id) # Передаем user_id

async def process_third_grok_response(message: types.Message, state: FSMContext, db: Database, logger_service):
    """Шаг 6c: Обрабатывает ответ на ТРЕТИЙ вопрос Grok, генерирует саммари и переходит к завершению."""
    user_id = message.from_user.id # <<< ID пользователя из его сообщения
    third_response = message.text.strip()
    if not third_response or len(third_response) < 2: await message.answer("Пожалуйста, попробуй ответить чуть подробнее."); return

    data = await state.get_data()
    third_grok_question = data.get("grok_question_3", "N/A")
    card_number = data.get("card_number", "N/A")
    user_request = data.get("user_request", "")

    await state.update_data(third_grok_response=third_response)
    await logger_service.log_action(user_id, "grok_response_provided", {"step": 3, "question": third_grok_question, "response": third_response, "card": card_number, "request": user_request})

    # Генерируем и отправляем саммари, передаем user_id
    await generate_and_send_summary(user_id=user_id, message=message, state=state, db=db, logger_service=logger_service)

    # Обновляем профиль пользователя после полного цикла вопросов
    try:
        await build_user_profile(user_id, db)
        logger.info(f"User profile updated after full Grok interaction for user {user_id}")
    except Exception as e:
        logger.error(f"Failed to update user profile after interaction for user {user_id}: {e}", exc_info=True)

    # Переходим к финальному замеру ресурса, передаем user_id
    await finish_interaction_flow(user_id=user_id, message=message, state=state, db=db, logger_service=logger_service) # Переход к Шагу 7

# --- Генерация и отправка саммари (ИСПРАВЛЕНО) ---
async def generate_and_send_summary(user_id: int, message: types.Message, state: FSMContext, db: Database, logger_service):
    """
    Генерирует саммари сессии и отправляет его пользователю. (ИСПРАВЛЕНО)
    Принимает user_id как обязательный аргумент.
    """
    if not isinstance(user_id, int): # Простая проверка
        logger.error("Invalid user_id passed to generate_and_send_summary")
        return

    data = await state.get_data()
    logger.info(f"Starting summary generation for user {user_id}")
    try:
        await message.bot.send_chat_action(user_id, 'typing') # Используем переданный user_id
    except Exception as e:
        logger.error(f"Failed send_chat_action (typing) to user {user_id} in generate_and_send_summary: {e}")
        # Продолжаем выполнение, даже если chat_action не прошел

    interaction_summary_data = {
        "user_request": data.get("user_request", ""),
        "card_number": data.get("card_number", "N/A"),
        "initial_response": data.get("initial_response"),
        "qna": [
            {"question": data.get("grok_question_1"), "answer": data.get("first_grok_response")},
            {"question": data.get("grok_question_2"), "answer": data.get("second_grok_response")},
            {"question": data.get("grok_question_3"), "answer": data.get("third_grok_response")}
        ]
    }
    # Оставляем в qna только те шаги, где был и вопрос, и ответ
    interaction_summary_data["qna"] = [item for item in interaction_summary_data["qna"] if item.get("question") and item.get("answer")]

    # Вызываем get_grok_summary с правильным user_id
    summary_text = await get_grok_summary(user_id, interaction_summary_data, db)

    # Проверяем результат и отправляем пользователю
    # Условие `not summary_text.startswith("...")` добавлено для обработки fallback-сообщений из get_grok_summary
    if summary_text and not summary_text.startswith(("Ошибка", "К сожалению", "Не получилось", "Произошла")):
        try:
            await message.answer(f"✨ Давай попробуем подвести итог нашей беседы:\n\n<i>{summary_text}</i>", parse_mode="HTML")
            await logger_service.log_action(user_id, "summary_sent", {"summary": summary_text})
        except Exception as e:
            logger.error(f"Failed to send summary message to user {user_id}: {e}", exc_info=True)
    else:
        # Если произошла ошибка в get_grok_summary (включая fallback), логируем ее
        await logger_service.log_action(user_id, "summary_failed", {"error_message": summary_text})
        try:
            # Отправляем пользователю сообщение об ошибке, если оно вернулось из get_grok_summary,
            # или стандартное "Спасибо", если вернулось None или что-то непредвиденное
            fallback_msg = summary_text if isinstance(summary_text, str) and summary_text.startswith(("Ошибка", "К сожалению", "Не получилось", "Произошла")) else "Спасибо за твои глубокие размышления!"
            await message.answer(fallback_msg)
        except Exception as e:
            logger.error(f"Failed to send fallback/error summary message to user {user_id}: {e}", exc_info=True)


# --- Шаг 7: Завершение (ИСПРАВЛЕНО) ---
async def finish_interaction_flow(user_id: int, message: types.Message, state: FSMContext, db: Database, logger_service):
    """
    Шаг 7: Запускает финальный замер ресурса. (ИСПРАВЛЕНО)
    Принимает user_id как обязательный аргумент.
    """
    if not isinstance(user_id, int): # Простая проверка
        logger.error("Invalid user_id passed to finish_interaction_flow")
        # Попытка безопасного завершения без вопроса
        try:
            # Пытаемся показать меню, если ID известен из message (маловероятно, но вдруг)
            menu_user_id = message.from_user.id if message and message.from_user else user_id
            await message.answer("Завершаю сессию...", reply_markup=await get_main_menu(menu_user_id, db))
            await state.clear()
            logger.warning(f"Cleared state for INVALID user_id reference after failing to send final resource question.")
        except Exception as clear_err:
             logger.error(f"Failed to clear state for INVALID user_id reference: {clear_err}", exc_info=True)
        return

    user_db_data = db.get_user(user_id) or {}
    name = user_db_data.get("name") or ""
    name = name.strip() if isinstance(name, str) else ""
    data = await state.get_data()
    initial_resource = data.get("initial_resource", "неизвестно")

    text = (f"{name}, наша работа с картой на сегодня подходит к концу. 🙏\nТы начала с состоянием '{initial_resource}'.\n\nКак ты чувствуешь себя <b>сейчас</b>? Как изменился твой уровень ресурса?"
            if name
            else f"Наша работа с картой на сегодня подходит к концу. 🙏\nТы начала с состоянием '{initial_resource}'.\n\nКак ты чувствуешь себя <b>сейчас</b>? Как изменился твой уровень ресурса?")

    buttons = [types.InlineKeyboardButton(text=label.split()[0], callback_data=key) for key, label in RESOURCE_LEVELS.items()]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[buttons])

    try:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(UserState.waiting_for_final_resource) # Переход к Шагу 8
    except Exception as e:
        logger.error(f"Failed to send final resource question to user {user_id}: {e}", exc_info=True)
        # Попытка очистить состояние, даже если сообщение не отправилось
        try:
            await message.answer("Не удалось задать финальный вопрос, но сессия завершена.", reply_markup=await get_main_menu(user_id, db)) # Показываем меню
            await state.clear()
            logger.warning(f"Cleared state for user {user_id} after failing to send final resource question.")
        except Exception as clear_err:
            logger.error(f"Failed to clear state for user {user_id} after message send failure: {clear_err}", exc_info=True)


# --- Шаг 8: Обработка финального ресурса ---
async def process_final_resource_callback(callback: types.CallbackQuery, state: FSMContext, db: Database, logger_service):
    """Шаг 7.5: Обрабатывает финальный выбор ресурса."""
    user_id = callback.from_user.id # <<< Получаем правильный user_id
    resource_choice_key = callback.data
    resource_choice_label = RESOURCE_LEVELS.get(resource_choice_key, "Неизвестно")
    await state.update_data(final_resource=resource_choice_label)
    await logger_service.log_action(user_id, "final_resource_selected", {"resource": resource_choice_label}) # Лог с правильным ID
    await callback.answer(f"Понял, твое состояние сейчас: {resource_choice_label.split()[0]}")
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e: logger.warning(f"Could not edit message reply markup (final resource) for user {user_id}: {e}")

    # Если ресурс низкий, предлагаем поддержку
    if resource_choice_key == "resource_low":
        try:
            await callback.message.answer("Мне жаль слышать, что ресурс на низком уровне...")
            await callback.message.bot.send_chat_action(user_id, 'typing')
            supportive_message_with_question = await get_grok_supportive_message(user_id, db)
            await callback.message.answer(supportive_message_with_question)
            await logger_service.log_action(user_id, "support_message_sent")
            await state.set_state(UserState.waiting_for_recharge_method) # Переход к Шагу 8.5
        except Exception as e:
             logger.error(f"Failed to send supportive message or set state for user {user_id}: {e}", exc_info=True)
             # Если поддержка не сработала, все равно переходим к фидбеку
             await show_final_feedback_and_menu(callback.message, state, db, logger_service, user_id=user_id)
    else:
        await callback.message.answer(f"Здорово, что твое состояние '{resource_choice_label}'! ✨")
        # Передаем правильный user_id в следующую функцию
        await show_final_feedback_and_menu(callback.message, state, db, logger_service, user_id=user_id) # Переход к Шагу 9

# --- Шаг 8.5: Обработка метода восстановления ---
async def process_recharge_method(message: types.Message, state: FSMContext, db: Database, logger_service):
    """Шаг 8.5: Обрабатывает ответ о способе восстановления ресурса."""
    user_id = message.from_user.id # <<< ID пользователя из его сообщения
    recharge_method_text = message.text.strip()
    user_db_data = db.get_user(user_id) or {}
    name = user_db_data.get("name") or ""
    name = name.strip() if isinstance(name, str) else ""
    if not recharge_method_text: await message.answer("Пожалуйста, напиши, что тебе помогает восстановиться."); return
    if len(recharge_method_text) < 5: await message.answer("Расскажи чуть подробнее, пожалуйста (хотя бы 5 символов)."); return

    try:
        now_iso = datetime.now(TIMEZONE).isoformat()
        db.add_recharge_method(user_id, recharge_method_text, now_iso)
        await state.update_data(recharge_method=recharge_method_text) # Сохраняем в state на всякий случай
        await logger_service.log_action(user_id, "recharge_method_provided", {"recharge_method": recharge_method_text})
        logger.info(f"Recharge method '{recharge_method_text}' added to separate table for user {user_id}")
    except Exception as e:
        logger.error(f"Failed to add recharge method to DB for user {user_id}: {e}", exc_info=True)

    final_text = (f"{name}, спасибо, что поделилась! Запомню это. Пожалуйста, найди возможность применить это для себя сегодня. Ты этого достоин(на). ❤️" if name else f"Спасибо, что поделилась! Запомню это. Пожалуйста, найди возможность применить это для себя сегодня. Ты этого достоин(на). ❤️")
    await message.answer(final_text, parse_mode="HTML") # parse_mode добавлен на всякий случай для эмодзи
    # Передаем user_id явно
    await show_final_feedback_and_menu(message, state, db, logger_service, user_id=user_id) # Переход к Шагу 9


# --- Шаг 9: Финальное сообщение, обратная связь, очистка (ИЗМЕНЕНА сигнатура) ---
async def show_final_feedback_and_menu(message: types.Message, state: FSMContext, db: Database, logger_service, user_id: int):
    """
    Шаг 9: Показывает финальное "Спасибо", кнопки обратной связи, меню и очищает состояние.
    Использует переданный user_id.
    """
    if not isinstance(user_id, int): # Проверка ID
        logger.error("Invalid user_id passed to show_final_feedback_and_menu")
        await state.clear() # Пытаемся очистить состояние
        return

    user_db_data = db.get_user(user_id) or {}
    name = user_db_data.get("name") or ""
    name = name.strip() if isinstance(name, str) else ""
    data = await state.get_data()
    card_number = data.get("card_number", 0)

    # Обновляем профиль (initial/final resource) - Используем правильный user_id
    try:
        final_profile_data = {
            "initial_resource": data.get("initial_resource"),
            "final_resource": data.get("final_resource"),
            "last_updated": datetime.now(TIMEZONE) # Используем текущее время
        }
        # Оставляем только не-None значения
        final_profile_data = {k: v for k, v in final_profile_data.items() if v is not None}
        if final_profile_data:
            db.update_user_profile(user_id, final_profile_data)
            logger.info(f"Final profile data (resources) saved for user {user_id} before state clear.") # Лог с правильным ID
    except Exception as e:
        logger.error(f"Error saving final profile resource data for user {user_id} before clear: {e}", exc_info=True)

    # Отправляем благодарность и главное меню
    try:
        await message.answer("Благодарю за твою открытость и уделённое время! 🙏 Работа с картами - это путь к себе.", reply_markup=await get_main_menu(user_id, db)) # Меню для правильного user_id
    except Exception as e:
        logger.error(f"Failed to send final thank you message to user {user_id}: {e}", exc_info=True)

    # Предлагаем оставить финальный фидбек
    feedback_text = f"{name}, и последний момент: насколько ценной для тебя оказалась эта сессия в целом? Удалось ли найти что-то важное или по-новому взглянуть на свой запрос?" if name else "И последний момент: насколько ценной для тебя оказалась эта сессия в целом? Удалось ли найти что-то важное или по-новому взглянуть на свой запрос?"
    feedback_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="👍 Да, помогло!", callback_data=f"feedback_v2_helped_{card_number}")],
        [types.InlineKeyboardButton(text="🤔 Было интересно", callback_data=f"feedback_v2_interesting_{card_number}")],
        [types.InlineKeyboardButton(text="😕 Не очень / Не хватило", callback_data=f"feedback_v2_notdeep_{card_number}")]
    ])
    try:
        await message.answer(feedback_text, reply_markup=feedback_keyboard)
        await logger_service.log_action(user_id, "final_feedback_prompted", {"card_session": card_number}) # Лог с правильным ID
    except Exception as e:
        logger.error(f"Failed to send final feedback prompt to user {user_id}: {e}", exc_info=True)

    # Очищаем состояние FSM
    try:
        current_state_before_clear = await state.get_state()
        current_data_before_clear = await state.get_data() # Получаем данные перед очисткой для лога
        logger.info(f"Clearing state for user {user_id} after card session. Current state: {current_state_before_clear}. Data: {current_data_before_clear}") # Лог с правильным ID
        await state.clear()
        current_state_after_clear = await state.get_state()
        logger.info(f"State cleared for user {user_id}. New state: {current_state_after_clear}") # Лог с правильным ID
    except Exception as e:
         logger.error(f"Failed to clear state for user {user_id}: {e}", exc_info=True)

# === Обработчик финальной обратной связи (👍/🤔/😕) ===
async def process_card_feedback(callback: types.CallbackQuery, state: FSMContext, db: Database, logger_service):
    user_id = callback.from_user.id
    user_data = db.get_user(user_id) or {}
    name = user_data.get("name") or ""
    name = name.strip() if isinstance(name, str) else ""
    callback_data = callback.data
    feedback_type = "unknown"
    card_number = 0

    try:
        parts = callback_data.split('_');
        if len(parts) >= 4 and parts[0] == 'feedback' and parts[1] == 'v2':
            feedback_type = parts[2]
            try:
                card_number = int(parts[-1])
            except ValueError:
                logger.error(f"Could not parse card number from feedback callback data: {callback_data} for user {user_id}")
                card_number = 0 # Используем 0 или другое значение по умолчанию

            text_map = {
                "helped": "Отлично! Рад, что наша беседа была для тебя полезной. 😊 Жду тебя завтра!",
                "interesting": "Здорово, что было интересно! Размышления и новые углы зрения - это тоже важный результат. 👍",
                "notdeep": f"{name}, спасибо за честность! Мне жаль, если не удалось копнуть достаточно глубоко в этот раз. Твои идеи в /feedback помогут мне учиться и развиваться." if name else "Спасибо за честность! Мне жаль, если не удалось копнуть достаточно глубоко в этот раз. Твои идеи в /feedback помогут мне учиться и развиваться."
            }
            text = text_map.get(feedback_type)

            if not text:
                logger.warning(f"Unknown feedback_v2 type: {feedback_type} received from user {user_id}")
                await callback.answer("Спасибо за ответ!", show_alert=False)
                try: await callback.message.edit_reply_markup(reply_markup=None)
                except Exception: pass
                return

            # Логируем действие
            await logger_service.log_action(user_id, "interaction_feedback_provided", {"card_session": card_number, "feedback": feedback_type})

            # Пытаемся убрать кнопки и отправить ответ
            try: await callback.message.edit_reply_markup(reply_markup=None)
            except Exception as e: logger.warning(f"Could not edit message reply markup (feedback buttons) for user {user_id}: {e}")

            try:
                await callback.message.answer(text, reply_markup=await get_main_menu(user_id, db))
                await callback.answer() # Отвечаем на колбэк без текста
            except Exception as e:
                logger.error(f"Failed to send feedback confirmation message to user {user_id}: {e}", exc_info=True)
                await callback.answer("Спасибо!", show_alert=False) # Простой ответ, если сообщение не ушло

        else:
             # Обработка неизвестного или старого формата callback_data
             logger.warning(f"Unknown or old feedback callback data format received: {callback_data} from user {user_id}")
             await callback.answer("Спасибо за ответ!", show_alert=False)
             try: await callback.message.edit_reply_markup(reply_markup=None)
             except Exception: pass
             return

    except Exception as e:
        logger.error(f"Error processing interaction feedback for user {user_id}: {e}", exc_info=True)
        try: await callback.answer("Произошла ошибка при обработке твоего ответа.", show_alert=True)
        except Exception: pass

# --- КОНЕЦ ФАЙЛА ---
