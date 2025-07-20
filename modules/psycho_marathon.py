# код/modules/psycho_marathon.py

import logging
import os
import json
import asyncio
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
from aiogram import Bot, types
from aiogram.fsm.context import FSMContext
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import MARATHONS, TUTORIALS, TIMEZONE, GOOGLE_SHEET_NAME
from .user_management import UserState
from database.db import Database
from modules.logging_service import LoggingService
from modules.quiz_handler import start_mak_quiz

logger = logging.getLogger(__name__)

# --- GOOGLE SHEETS AUTHENTICATION & CACHING ---
schedule_cache = {}
cache_timestamp = None
CACHE_TTL = timedelta(minutes=5)

def get_gsheet_client():
    """Настраивает и возвращает клиент для работы с Google Sheets."""
    try:
        creds_json_str = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if not creds_json_str:
            logger.error("Google credentials JSON not found in environment variables.")
            return None
        creds_dict = json.loads(creds_json_str)
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly"
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        logger.error(f"Failed to authenticate with Google Sheets: {e}", exc_info=True)
        return None

def get_marathon_schedule_from_sheet():
    """Загружает расписание всех марафонов из Google Таблицы с кэшированием."""
    global schedule_cache, cache_timestamp
    now = datetime.now()

    if schedule_cache and cache_timestamp and (now - cache_timestamp < CACHE_TTL):
        logger.info("Using cached marathon schedule.")
        return schedule_cache

    client = get_gsheet_client()
    if not client:
        return {}
    try:
        spreadsheet = client.open(GOOGLE_SHEET_NAME)
        sheet = spreadsheet.worksheet("MarathonContent")
        records = sheet.get_all_records()
        
        schedule = {}
        for record in records:
            program_id = record.get("marathon_id")
            if program_id:
                if program_id not in schedule:
                    schedule[program_id] = []
                schedule[program_id].append(record)
        
        for mid in schedule:
            schedule[mid].sort(key=lambda x: (int(x.get('day', 0)), int(x.get('post_id', 0))))

        schedule_cache = schedule
        cache_timestamp = now
        logger.info(f"Successfully loaded and cached schedule for {len(schedule)} programs from Google Sheet.")
        return schedule
    except gspread.exceptions.WorksheetNotFound:
        logger.error(f"Worksheet 'MarathonContent' not found.")
        return {}
    except Exception as e:
        logger.error(f"Failed to read from Google Sheet: {e}", exc_info=True)
        return {}

# --- POST SENDING LOGIC ---
async def send_post_and_schedule_next(bot: Bot, scheduler: AsyncIOScheduler, user_id: int, program_id: str, post_id_to_send: int, state: FSMContext, logger_service: LoggingService):
    """
    Отправляет текущий пост и планирует/предлагает следующий.
    """
    logger.info(f"send_post_and_schedule_next вызван для user_id={user_id}, program_id={program_id}, post_id_to_send={post_id_to_send}")
    schedule = get_marathon_schedule_from_sheet().get(program_id, [])
    logger.info(f"Загружено {len(schedule)} постов для программы {program_id}")
    current_post_data = next((p for p in schedule if p.get('post_id') and int(p.get('post_id')) == post_id_to_send), None)
    
    if not current_post_data:
        logger.warning(f"Post ID {post_id_to_send} not found for {program_id}. Stopping for user {user_id}.")
        return

    try:
        # --- ИЗМЕНЕНИЕ: ЛОГИКА ДЛЯ ОПРОСОВ ---
        poll_question = current_post_data.get("poll_question", "")
        if poll_question:
            poll_options_str = current_post_data.get("poll_options", "")
            options = [opt.strip() for opt in poll_options_str.split(';') if opt.strip()]
            is_anonymous = str(current_post_data.get("poll_is_anonymous", "TRUE")).upper() == "TRUE"
            
            if len(options) >= 2:
                await bot.send_poll(
                    chat_id=user_id,
                    question=poll_question,
                    options=options,
                    is_anonymous=is_anonymous
                )
                logger.info(f"Sent poll {program_id}/{current_post_data['day']}/{post_id_to_send} to user {user_id}")
            else:
                logger.warning(f"Not enough options to create a poll for post ID {post_id_to_send}. Skipping.")

        # --- Старая логика для текста/картинок ---
        else:
            text = current_post_data.get("text", "").replace("<br>", "\n")
            image_url = current_post_data.get("image_url", "")
            
            current_index = schedule.index(current_post_data)
            next_index = current_index + 1
            reply_markup = None

            if next_index < len(schedule):
                next_post_data = schedule[next_index]
                if next_post_data.get("trigger_type") == "button":
                    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="Дальше ➡️", callback_data=f"next_step_{program_id}_{next_post_data['post_id']}")]])
                    reply_markup = keyboard

            if image_url:
                # Ограничиваем caption до 1024 символов
                caption = text[:1024] if len(text) > 1024 else text
                await bot.send_photo(user_id, photo=image_url, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
                
                # Если текст длиннее 1024 символов, отправляем остаток отдельным сообщением
                if len(text) > 1024:
                    remaining_text = text[1024:]
                    await bot.send_message(user_id, text=remaining_text, parse_mode="HTML")
            elif text:
                await bot.send_message(user_id, text=text, parse_mode="HTML", reply_markup=reply_markup)
            
            logger.info(f"Sent post {program_id}/{current_post_data['day']}/{post_id_to_send} to user {user_id}")

        await state.update_data(last_post_id=current_post_data['post_id'])
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---

    except Exception as e:
        logger.error(f"Failed to send post content to user {user_id}: {e}", exc_info=True)
        return

    # Логика для следующего шага остается прежней
    current_index = schedule.index(current_post_data)
    next_index = current_index + 1
    if next_index < len(schedule):
        next_post_data = schedule[next_index]
        if next_post_data.get("trigger_type") == "delay":
            trigger_value = next_post_data.get("trigger_value")
            try:
                delay_seconds = 0
                if 'm' in str(trigger_value): delay_seconds = int(str(trigger_value).replace('m', '')) * 60
                elif 'h' in str(trigger_value): delay_seconds = int(str(trigger_value).replace('h', '')) * 3600
                
                run_date = datetime.now(TIMEZONE) + timedelta(seconds=delay_seconds)
                scheduler.add_job(send_post_and_schedule_next, 'date', run_date=run_date, args=[bot, scheduler, user_id, program_id, next_post_data['post_id'], state, logger_service], id=f"prog:{user_id}:{program_id}:{next_post_data['post_id']}")
                logger.info(f"Scheduled next post for user {user_id} at {run_date.strftime('%Y-%m-%d %H:%M:%S')}")
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid delay format '{trigger_value}' for post {next_post_data.get('post_id')}: {e}")
    else:
        logger.info(f"User {user_id} has completed program '{program_id}'.")
        # --- ИЗМЕНЕНИЕ: Запускаем опросник вместо простого завершения ---
        if program_id == "mak_tutorial":
            await bot.send_message(user_id, "Вы завершили основной блок обучения! 🎉")
            # Передаем message-like объект для старта квиза
            mock_message = types.Message(
                message_id=1,
                date=datetime.now(),
                chat=types.Chat(id=user_id, type="private"), 
                from_user=types.User(id=user_id, is_bot=False, first_name="User")
            )
            await start_mak_quiz(mock_message, state, logger_service, bot)
        else:
            await bot.send_message(user_id, "Поздравляем! Вы завершили этот блок! 🎉")
            await state.clear()

async def handle_training_command(message: types.Message, state: FSMContext, db: Database, logger_service: LoggingService):
    logger.info(f"handle_training_command вызван для user_id={message.from_user.id}")
    await state.clear()
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="Выбрать обучение", callback_data="list_tutorials")]])
    logger.info("Создана клавиатура для обучения с callback_data=list_tutorials")
    await message.answer("Здесь собраны обучающие курсы. ✨", reply_markup=keyboard)
    logger.info("Отправлено сообщение с обучающими курсами")

async def handle_marathon_command(message: types.Message, state: FSMContext):
    await state.clear()
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="Выбрать марафон", callback_data="list_marathons")]])
    await message.answer("Здесь вы можете начать один из наших марафонов. 🏃‍♀️", reply_markup=keyboard)

async def list_programs_callback(callback: types.CallbackQuery, state: FSMContext):
    logger.info(f"list_programs_callback вызван с callback_data={callback.data}")
    program_type = callback.data.split("_")[1]
    logger.info(f"Извлечен program_type={program_type}")
    
    programs = TUTORIALS if program_type == "tutorials" else MARATHONS
    logger.info(f"Выбраны программы: {list(programs.keys())}")
    
    title = "Выберите обучающий курс:" if program_type == "tutorials" else "Выберите марафон:"
    buttons = [[types.InlineKeyboardButton(text=settings["name"], callback_data=f"program_{prog_id}")] for prog_id, settings in programs.items()]
    logger.info(f"Создано {len(buttons)} кнопок: {[btn[0].text for btn in buttons]}")
    
    await callback.message.edit_text(title, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()
    logger.info("list_programs_callback завершен успешно")

async def program_selection_callback(callback: types.CallbackQuery, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler, logger_service: LoggingService):
    logger.info(f"program_selection_callback вызван с callback_data={callback.data}")
    # Убираем "program_" и получаем program_id
    program_id = callback.data.replace("program_", "")
    user_id = callback.from_user.id
    logger.info(f"Извлечен program_id={program_id}, user_id={user_id}")
    
    all_programs = {**TUTORIALS, **MARATHONS}
    logger.info(f"Доступные программы: {list(all_programs.keys())}")

    if program_id in all_programs:
        program_name = all_programs[program_id]["name"]
        logger.info(f"Найдена программа: {program_name}")
        
        await state.set_state(UserState.in_marathon)
        await state.update_data(current_program=program_id)
        await callback.message.edit_text(f"Вы начали программу \"{program_name}\"! Отправляю первое сообщение... 🚀")
        
        schedule = get_marathon_schedule_from_sheet().get(program_id, [])
        logger.info(f"Загружено {len(schedule)} постов для программы {program_id}")
        
        first_post = next((p for p in schedule if p.get('day') and int(p.get('day')) == 1 and p.get('trigger_type') == 'immediate'), None)
        logger.info(f"Первый пост: {first_post}")

        if first_post:
            logger.info(f"Запускаю send_post_and_schedule_next для первого поста")
            asyncio.create_task(send_post_and_schedule_next(bot, scheduler, user_id, program_id, first_post['post_id'], state, logger_service))
        else:
            logger.warning(f"Не найдено стартовое сообщение для программы {program_id}")
            await callback.message.answer("Не найдено стартовое сообщение для этой программы.")
    else:
        logger.error(f"Программа {program_id} не найдена в списке доступных программ")
        await callback.message.edit_text("К сожалению, такая программа не найдена.")
    await callback.answer()
    logger.info("program_selection_callback завершен")

async def next_step_callback(callback: types.CallbackQuery, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler, logger_service: LoggingService):
    user_id = callback.from_user.id
    logger.info(f"next_step_callback вызван для user_id={user_id} с callback_data: {callback.data}")
    
    try:
        # Убираем "next_step_" и разбираем остальное
        data_without_prefix = callback.data.replace("next_step_", "")
        logger.info(f"callback_data без префикса: {data_without_prefix}")
        
        # Ищем последнее подчёркивание, которое отделяет program_id от post_id
        last_underscore_index = data_without_prefix.rfind("_")
        if last_underscore_index == -1:
            logger.error(f"Не найдено подчёркивание в callback_data: {data_without_prefix}")
            await callback.answer("Ошибка! Не могу определить следующий шаг.")
            return
            
        program_id = data_without_prefix[:last_underscore_index]
        next_post_id_str = data_without_prefix[last_underscore_index + 1:]
        
        logger.info(f"Извлеченные данные: program_id={program_id}, next_post_id_str={next_post_id_str}")
        
        next_post_id = int(next_post_id_str)
        logger.info(f"Преобразованный next_post_id: {next_post_id}")
        
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Отправляю следующий шаг...")
        
        logger.info(f"Запускаю send_post_and_schedule_next для user_id={user_id}, program_id={program_id}, next_post_id={next_post_id}")
        asyncio.create_task(send_post_and_schedule_next(bot, scheduler, user_id, program_id, next_post_id, state, logger_service))
        
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid callback data for next step: {callback.data}, error: {e}")
        await callback.answer("Ошибка! Не могу определить следующий шаг.")