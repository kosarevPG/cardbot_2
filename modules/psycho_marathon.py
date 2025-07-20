# код/modules/psycho_marathon.py

import logging
import os
import json
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
from aiogram import Bot, types
from aiogram.fsm.context import FSMContext
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import MARATHONS, TIMEZONE, GOOGLE_SHEET_NAME
from .user_management import UserState
from database.db import Database

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
        scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
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
        
        schedule_cache = schedule
        cache_timestamp = now
        logger.info(f"Successfully loaded and cached schedule for {len(schedule)} marathons from Google Sheet.")
        return schedule
    except Exception as e:
        logger.error(f"Failed to read from Google Sheet '{GOOGLE_SHEET_NAME}': {e}", exc_info=True)
        return {}

# --- POST SENDING LOGIC ---
async def send_post(bot: Bot, post_data: dict, chat_id: int):
    """Формирует и отправляет пост, основываясь на данных из таблицы."""
    try:
        text = post_data.get("text", "")
        image_url = post_data.get("image_url", "")
        
        if image_url:
            await bot.send_photo(chat_id=chat_id, photo=image_url, caption=text, parse_mode="HTML")
        elif text:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
            
        logger.info(f"Sent post day {post_data.get('day')}-post {post_data.get('post_id')} to chat {chat_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to send post content to chat {chat_id}: {e}", exc_info=True)
        return False


# --- SCHEDULER LOGIC ---
async def schedule_marathon_posts(bot: Bot):
    """Настраивает и запускает планировщик, используя данные из Google Sheets."""
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    logger.info("Marathon scheduler initialized.")
    
    schedule_data = get_marathon_schedule_from_sheet()

    for marathon_id, posts in schedule_data.items():
        marathon_config = MARATHONS.get(marathon_id)
        if not marathon_config:
            continue

        chat_id = marathon_config.get("chat_id") # Пока не используется, т.к. шлем в личку
        if not chat_id:
             logger.warning(f"chat_id not set for marathon '{marathon_id}' in config.py")
             continue

        for post in posts:
            if post.get('trigger_type') == 'time':
                try:
                    # Эта логика для отправки в общий канал по датам, для вечнозеленого марафона она будет другой
                    # Пока оставляем ее пустой, т.к. фокус на персональных марафонах
                    pass
                except (ValueError, KeyError) as e:
                    logger.error(f"Error scheduling time-based post for marathon '{marathon_id}'. Invalid data: {post}. Error: {e}")

    if scheduler.get_jobs():
        scheduler.start()
        logger.info("Marathon scheduler started with time-based jobs.")
    else:
        logger.info("No time-based marathon posts to schedule.")


# --- USER INTERACTION HANDLERS ---
async def handle_marathon_command(message: types.Message, state: FSMContext):
    """Обрабатывает команду /marathon, предлагает выбор."""
    await state.clear()
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Выбрать марафон", callback_data="list_marathons")]
    ])
    await message.answer("Добро пожаловать в раздел марафонов! ✨", reply_markup=keyboard)


async def list_marathons_callback(callback: types.CallbackQuery, state: FSMContext):
    """Показывает список доступных марафонов из конфига."""
    buttons = []
    for marathon_id, settings in MARATHONS.items():
        buttons.append([types.InlineKeyboardButton(text=settings["name"], callback_data=f"marathon_{marathon_id}")])
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("Выберите марафон, который хотите начать:", reply_markup=keyboard)
    await callback.answer()


async def marathon_selection_callback(callback: types.CallbackQuery, state: FSMContext, bot: Bot, db: Database):
    """Обрабатывает выбор марафона и отправляет первый пост."""
    marathon_id = callback.data.split("_")[1]
    user_id = callback.from_user.id

    if marathon_id in MARATHONS:
        marathon_name = MARATHONS[marathon_id]["name"]
        await state.update_data(current_marathon=marathon_id, current_day=1, last_post_id=0)
        await state.set_state(UserState.in_marathon)
        
        await callback.message.edit_text(f"Вы начали марафон \"{marathon_name}\"! Отправляю первое задание... 🏃‍♀️")
        
        schedule = get_marathon_schedule_from_sheet().get(marathon_id, [])
        first_post = next((p for p in schedule if p.get('day') == 1 and p.get('trigger_type') == 'immediate'), None)

        if first_post:
            await send_post(bot, first_post, user_id)
            await state.update_data(last_post_id=first_post.get("post_id", 0))
            # Здесь в будущем можно будет добавить кнопку "Дальше"
        else:
            await callback.message.answer("Не найдено стартовое сообщение для этого марафона.")

    else:
        await callback.message.edit_text("К сожалению, такой марафон не найден.")
    await callback.answer()