# код/main.py

import subprocess
import shlex
import threading
import os
from dotenv import load_dotenv
load_dotenv()

def run_sqlite_web():
    db_path = "/data/bot.db"
    port = os.environ.get("PORT", "80")
    host = "0.0.0.0"
    command = f"sqlite_web {shlex.quote(db_path)} --host {shlex.quote(host)} --port {shlex.quote(port)} --no-browser"
    print(f"Starting sqlite_web process with command: {command}", flush=True)
    try:
        process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True)
        print(f"sqlite_web process started with PID: {process.pid}", flush=True)
        # Просто запускаем и не ждем завершения в основном потоке
    except FileNotFoundError:
         print(f"CRITICAL error: 'sqlite_web' command not found. Is it installed and in PATH?", flush=True)
    except Exception as e:
        print(f"CRITICAL error starting/running sqlite_web process: {e}", flush=True)

threading.Thread(target=run_sqlite_web, daemon=True).start()

import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- Импорты из проекта ---
from config import TOKEN, ADMIN_ID, DATA_DIR
from database.db import Database
from modules.logging_service import LoggingService
from modules.notification_service import NotificationService
from modules.user_management import UserState, UserManager
from modules.card_of_the_day import *
from modules.evening_reflection import *
from modules.psycho_marathon import *
from strings import *

# --- Настройка логирования ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Обработчики команд ---

async def handle_start(message: types.Message, state: FSMContext, db: Database, user_manager: UserManager, logger_service: LoggingService, command: CommandObject | None = None):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username or ""
    await logger_service.log_action(user_id, "start_command", {"args": command.args if command else None})
    user_data = db.get_user(user_id)
    if user_data.get("username") != username: db.update_user(user_id, {"username": username})

    if command and command.args and command.args.startswith("ref_"):
        try:
            referrer_id = int(command.args[4:])
            if referrer_id != user_id and db.add_referral(referrer_id, user_id):
                 referrer_data = db.get_user(referrer_id)
                 if referrer_data and not referrer_data.get("bonus_available"):
                     await user_manager.set_bonus_available(referrer_id, True)
                     ref_name = referrer_data.get("name", "Друг")
                     await bot.send_message(referrer_id, REFERRAL_BONUS_MESSAGE.format(ref_name=ref_name), reply_markup=await get_main_menu(referrer_id, db))
                     await logger_service.log_action(referrer_id, "referral_bonus_granted", {"referred_user": user_id})
        except Exception as e:
            logger.warning(f"Invalid referral code processing '{command.args}': {e}")
            
    if not user_data.get("name"):
        await message.answer(START_NEW_USER_MESSAGE, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text=BUTTON_SKIP, callback_data="skip_name")]]))
        await state.set_state(UserState.waiting_for_name)
    else:
        await message.answer(START_EXISTING_USER_MESSAGE.format(name=user_data["name"]), reply_markup=await get_main_menu(user_id, db))

async def handle_name(message: types.Message, state: FSMContext, db: Database, logger_service: LoggingService):
    user_id = message.from_user.id
    name = db.get_user(user_id).get("name")
    text = (NAME_CURRENT_MESSAGE.format(name=name) if name else NAME_NEW_MESSAGE) + NAME_INSTRUCTION
    await message.answer(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text=BUTTON_SKIP, callback_data="skip_name")]]))
    await state.set_state(UserState.waiting_for_name)
    await logger_service.log_action(user_id, "name_change_initiated")

async def handle_remind(message: types.Message, state: FSMContext, db: Database, logger_service: LoggingService):
    user_id = message.from_user.id
    user_data = db.get_user(user_id)
    name = user_data.get("name", DEFAULT_NAME)
    morning_reminder = user_data.get("reminder_time")
    evening_reminder = user_data.get("reminder_time_evening")
    morning_text = MORNING_REMINDER_TEXT.format(time=morning_reminder) if morning_reminder else MORNING_REMINDER_DISABLED
    evening_text = EVENING_REMINDER_TEXT.format(time=evening_reminder) if evening_reminder else EVENING_REMINDER_DISABLED
    text = REMIND_MESSAGE.format(name=name, purpose_text=REMIND_PURPOSE_TEXT, instruction_text=REMIND_INSTRUCTION_TEXT.format(morning_text=morning_text, evening_text=evening_text))
    await message.answer(text)
    await state.set_state(UserState.waiting_for_morning_reminder_time)

# --- Регистрация всех обработчиков ---
def register_handlers(dp: Dispatcher):
    logger.info("Registering handlers...")
    
    # Команды
    dp.message.register(handle_start, Command("start"), StateFilter("*"))
    dp.message.register(handle_name, Command("name"), StateFilter("*"))
    dp.message.register(handle_remind, Command("remind"), StateFilter("*"))
    dp.message.register(handle_training_command, Command("training"), StateFilter("*"))
    dp.message.register(handle_marathon_command, Command("marathon"), StateFilter("*"))

    # Текстовые кнопки меню
    dp.message.register(handle_training_command, F.text == "🎓 Обучение", StateFilter("*"))
    dp.message.register(handle_card_request, F.text == "✨ Карта дня", StateFilter("*"))
    dp.message.register(start_evening_reflection, F.text == "🌙 Итог дня", StateFilter("*"))
    
    # Флоу марафонов и обучения
    dp.callback_query.register(list_programs_callback, F.data.startswith("list_"), StateFilter("*"))
    dp.callback_query.register(program_selection_callback, F.data.startswith("program_"), StateFilter("*"))
    dp.callback_query.register(next_step_callback, F.data.startswith("next_step_"), StateFilter("*"))

    # Флоу Карты Дня
    dp.callback_query.register(process_initial_resource_callback, UserState.waiting_for_initial_resource, F.data.startswith("resource_"))
    dp.callback_query.register(process_request_type_callback, UserState.waiting_for_request_type_choice, F.data.startswith("request_type_"))
    dp.message.register(process_request_text, UserState.waiting_for_request_text_input)
    dp.message.register(process_initial_response, UserState.waiting_for_initial_response)
    dp.callback_query.register(process_exploration_choice_callback, UserState.waiting_for_exploration_choice, F.data.startswith("explore_"))
    dp.message.register(process_first_grok_response, UserState.waiting_for_first_grok_response)
    dp.message.register(process_second_grok_response, UserState.waiting_for_second_grok_response)
    dp.message.register(process_third_grok_response, UserState.waiting_for_third_grok_response)
    dp.callback_query.register(process_final_resource_callback, UserState.waiting_for_final_resource, F.data.startswith("resource_"))
    dp.message.register(process_recharge_method, UserState.waiting_for_recharge_method)
    dp.callback_query.register(process_card_feedback, F.data.startswith("feedback_v2_"), StateFilter("*"))
    
    # Флоу Итога Дня
    dp.message.register(process_good_moments, UserState.waiting_for_good_moments)
    dp.message.register(process_gratitude, UserState.waiting_for_gratitude)
    dp.message.register(process_hard_moments, UserState.waiting_for_hard_moments)
    
    logger.info("Handlers registered successfully.")

# --- Запуск бота ---
async def main():
    logger.info("Starting bot...")
    
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    db = Database(path=os.path.join(DATA_DIR, "bot.db"))
    db.bot = bot
    
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.start()
    
    # Передаем зависимости в диспетчер
    dp["db"] = db
    dp["logger_service"] = LoggingService(db)
    dp["user_manager"] = UserManager(db)
    dp["bot"] = bot
    dp["scheduler"] = scheduler

    commands = [
        types.BotCommand(command="start", description="🔄 Перезагрузка"),
        types.BotCommand(command="training", description="🎓 Обучение по МАК"),
        types.BotCommand(command="marathon", description="🏃‍♀️ Выбрать марафон"),
        types.BotCommand(command="name", description="👩🏼 Указать имя"),
        types.BotCommand(command="remind", description="⏰ Настроить напоминания"),
    ]
    await bot.set_my_commands(commands)

    register_handlers(dp)
    
    notifier = NotificationService(bot, db)
    reminder_task = asyncio.create_task(notifier.check_reminders())

    logger.info("Starting polling...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        logger.info("Stopping bot...")
        reminder_task.cancel()
        scheduler.shutdown()
        await asyncio.sleep(0.1)
        if db.conn:
            db.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped manually.")