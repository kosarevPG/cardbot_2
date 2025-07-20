# код/modules/psycho_marathon.py

import asyncio
import logging
import os
import json
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
from aiogram import Bot, types
from aiogram.fsm.context import FSMContext
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import MARATHONS, TUTORIALS, TIMEZONE, GOOGLE_SHEET_NAME # <--- Импортируем TUTORIALS
from .user_management import UserState
from database.db import Database
from modules.logging_service import LoggingService

logger = logging.getLogger(__name__)

# ... (Google Sheets functions remain the same) ...
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
            marathon_id = record.get("marathon_id")
            if marathon_id:
                if marathon_id not in schedule:
                    schedule[marathon_id] = []
                schedule[marathon_id].append(record)
        
        for mid in schedule:
            schedule[mid].sort(key=lambda x: (int(x.get('day', 0)), int(x.get('post_id', 0))))

        schedule_cache = schedule
        cache_timestamp = now
        logger.info(f"Successfully loaded and cached schedule for {len(schedule)} marathons from Google Sheet.")
        return schedule
    except gspread.exceptions.WorksheetNotFound:
        logger.error(f"Worksheet 'MarathonContent' not found in Google Sheet '{GOOGLE_SHEET_NAME}'. Please check the tab name.")
        return {}
    except Exception as e:
        logger.error(f"Failed to read from Google Sheet '{GOOGLE_SHEET_NAME}': {e}", exc_info=True)
        return {}

# --- POST SENDING LOGIC ---
async def send_post_and_schedule_next(bot: Bot, scheduler: AsyncIOScheduler, user_id: int, program_id: str, post_id_to_send: int, state: FSMContext):
    """
    Отправляет текущий пост и планирует/предлагает следующий.
    """
    schedule = get_marathon_schedule_from_sheet().get(program_id, [])
    current_post_data = next((p for p in schedule if p.get('post_id') and int(p.get('post_id')) == post_id_to_send), None)
    
    if not current_post_data:
        logger.warning(f"Could not find post with ID {post_id_to_send} for program {program_id}. Stopping chain for user {user_id}.")
        return

    try:
        text = current_post_data.get("text", "").replace("<br>", "\n")
        image_url = current_post_data.get("image_url", "")
        
        current_index = schedule.index(current_post_data)
        next_index = current_index + 1
        reply_markup = None

        if next_index < len(schedule):
            next_post_data = schedule[next_index]
            if next_post_data.get("trigger_type") == "button":
                keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="Дальше ➡️", callback_data=f"next_step_{program_id}_{next_post_data['post_id']}")]
                ])
                reply_markup = keyboard

        if image_url:
            await bot.send_photo(user_id, photo=image_url, caption=text, parse_mode="HTML", reply_markup=reply_markup)
        elif text:
            await bot.send_message(user_id, text=text, parse_mode="HTML", reply_markup=reply_markup)
        
        await state.update_data(last_post_id=current_post_data['post_id'])
        logger.info(f"Sent post {program_id}/{current_post_data['day']}/{post_id_to_send} to user {user_id}")

    except Exception as e:
        logger.error(f"Failed to send post content to user {user_id}: {e}", exc_info=True)
        return

    if next_index < len(schedule):
        next_post_data = schedule[next_index]
        if next_post_data.get("trigger_type") == "delay":
            trigger_value = next_post_data.get("trigger_value")
            try:
                delay_seconds = 0
                if 'm' in str(trigger_value):
                    delay_seconds = int(str(trigger_value).replace('m', '')) * 60
                elif 'h' in str(trigger_value):
                    delay_seconds = int(str(trigger_value).replace('h', '')) * 3600
                
                run_date = datetime.now(TIMEZONE) + timedelta(seconds=delay_seconds)
                scheduler.add_job(
                    send_post_and_schedule_next,
                    'date',
                    run_date=run_date,
                    args=[bot, scheduler, user_id, program_id, next_post_data['post_id'], state],
                    id=f"program:{user_id}:{program_id}:{next_post_data['post_id']}"
                )
                logger.info(f"Scheduled next post for user {user_id} at {run_date.strftime('%Y-%m-%d %H:%M:%S')}")
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid delay format '{trigger_value}' for post {next_post_data.get('post_id')}: {e}")
    else:
        await bot.send_message(user_id, "Поздравляем! Вы завершили этот блок! 🎉")
        logger.info(f"User {user_id} has completed program '{program_id}'.")
        await state.clear()


# --- USER INTERACTION HANDLERS ---
async def handle_training_command(message: types.Message, state: FSMContext, db: Database, logger_service: LoggingService):
    await state.clear()
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Выбрать обучение", callback_data="list_tutorials")]
    ])
    await message.answer("Здесь собраны обучающие курсы. ✨", reply_markup=keyboard)

async def handle_marathon_command(message: types.Message, state: FSMContext):
    await state.clear()
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Выбрать марафон", callback_data="list_marathons")]
    ])
    await message.answer("Здесь вы можете начать один из наших марафонов. 🏃‍♀️", reply_markup=keyboard)


async def list_programs_callback(callback: types.CallbackQuery, state: FSMContext):
    program_type = callback.data.split("_")[1]
    
    if program_type == "tutorials":
        programs = TUTORIALS
        title = "Выберите обучающий курс:"
    elif program_type == "marathons":
        programs = MARATHONS
        title = "Выберите марафон:"
    else:
        await callback.answer("Неизвестный тип программы.", show_alert=True)
        return

    buttons = []
    for program_id, settings in programs.items():
        buttons.append([types.InlineKeyboardButton(text=settings["name"], callback_data=f"program_{program_id}")])
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(title, reply_markup=keyboard)
    await callback.answer()


async def program_selection_callback(callback: types.CallbackQuery, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler):
    program_id = callback.data.split("_")[1]
    user_id = callback.from_user.id

    all_programs = {**TUTORIALS, **MARATHONS}

    if program_id in all_programs:
        program_name = all_programs[program_id]["name"]
        await state.set_state(UserState.in_marathon) # Используем одно состояние для обоих
        await state.update_data(current_program=program_id)
        
        await callback.message.edit_text(f"Вы начали программу \"{program_name}\"! Отправляю первое сообщение... 🚀")
        
        schedule = get_marathon_schedule_from_sheet().get(program_id, [])
        first_post = next((p for p in schedule if p.get('day') and int(p.get('day')) == 1 and p.get('trigger_type') == 'immediate'), None)

        if first_post:
            asyncio.create_task(send_post_and_schedule_next(bot, scheduler, user_id, program_id, first_post['post_id'], state))
        else:
            await callback.message.answer("Не найдено стартовое сообщение для этой программы.")
    else:
        await callback.message.edit_text("К сожалению, такая программа не найдена.")
    await callback.answer()

async def next_step_callback(callback: types.CallbackQuery, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler):
    """Обрабатывает нажатие кнопки 'Дальше'."""
    user_id = callback.from_user.id
    
    try:
        _, _, program_id, next_post_id_str = callback.data.split("_")
        next_post_id = int(next_post_id_str)
    except (ValueError, IndexError):
        logger.error(f"Invalid callback data for next step: {callback.data}")
        await callback.answer("Ошибка! Не могу определить следующий шаг.")
        return

    await callback.message.edit_reply_markup(reply_markup=None) # Убираем кнопку
    await callback.answer("Отправляю следующий шаг...")

    asyncio.create_task(send_post_and_schedule_next(bot, scheduler, user_id, program_id, next_post_id, state))