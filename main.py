# код/main.py

import subprocess
import shlex # Также импортируем shlex для безопасной обработки аргументов
import threading
import os
from dotenv import load_dotenv
load_dotenv()

def run_sqlite_web():
    db_path = "/data/bot.db"
    port = os.environ.get("PORT", "80")
    host = "0.0.0.0"
    # Используем аргумент --password без значения, если пароль не нужен или задается иначе
    command = f"sqlite_web {shlex.quote(db_path)} --host {shlex.quote(host)} --port {shlex.quote(port)} --no-browser"

    print(f"Starting sqlite_web process with command: {command}", flush=True)
    try:
        # shell=True может быть рискованным, лучше передавать список аргументов, если возможно
        process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True)
        print(f"sqlite_web process started with PID: {process.pid}", flush=True)

        # Читаем stdout в реальном времени
        for line in iter(process.stdout.readline, ''):
            print(f"[sqlite_web stdout]: {line.strip()}", flush=True)

        # Читаем stderr в реальном времени (после завершения stdout)
        for line in iter(process.stderr.readline, ''):
            print(f"[sqlite_web stderr]: {line.strip()}", flush=True)

        # Ждем завершения процесса (если он вдруг завершится)
        process.wait()
        print(f"sqlite_web process exited with code: {process.returncode}", flush=True)

    except FileNotFoundError:
         print(f"CRITICAL error: 'sqlite_web' command not found. Is it installed and in PATH?", flush=True)
    except Exception as e:
        print(f"CRITICAL error starting/running sqlite_web process: {e}", flush=True)

# Запуск потока остается тем же
t = threading.Thread(target=run_sqlite_web, daemon=True)
t.start()

import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter, CommandObject
from aiogram.exceptions import TelegramAPIError
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
# --- ДОБАВЛЯЕМ ИМПОРТ State ---
from aiogram.fsm.state import State, StatesGroup
# --- КОНЕЦ ИЗМЕНЕНИЯ ---
from aiogram.fsm.storage.memory import MemoryStorage
from functools import partial
import pytz # Убедимся, что pytz импортирован

# --- Импорты из проекта ---
from config import (
    TOKEN, CHANNEL_ID, ADMIN_ID, UNIVERSE_ADVICE, BOT_LINK,
    TIMEZONE, NO_LOGS_USERS, DATA_DIR
)
# База данных и Сервисы
from database.db import Database
from modules.logging_service import LoggingService
from modules.notification_service import NotificationService
# Убираем импорт State отсюда, т.к. он теперь выше
from modules.user_management import UserState, UserManager
from modules.ai_service import build_user_profile

# Модуль Карты Дня
from modules.card_of_the_day import (
    get_main_menu, handle_card_request, process_initial_resource_callback,
    process_request_type_callback, process_request_text, process_initial_response,
    process_exploration_choice_callback, process_first_grok_response,
    process_second_grok_response, process_third_grok_response,
    process_final_resource_callback, process_recharge_method, process_card_feedback
)

# Модуль Вечерней Рефлексии
# Импортируем функцию для старта и обработчики состояний
from modules.evening_reflection import (
    start_evening_reflection,
    process_good_moments,      # <--- Добавлено
    process_gratitude,       # <--- Добавлено
    process_hard_moments     # <--- Добавлено
    # reflection_router больше не импортируем здесь
)

# --- Стандартные импорты ---
import random
from datetime import datetime, timedelta, time, date # Добавляем time, date
import os
import json
import logging
import sqlite3

# --- Настройка логирования ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Инициализация ---
# ... (инициализация bot, storage, db, сервисов как раньше) ...
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
os.makedirs(DATA_DIR, exist_ok=True)
db_path = os.path.join(DATA_DIR, "bot.db")
logger.info(f"Initializing database at: {db_path}")
print(f"Initializing database at: {db_path}")
try:
    db = Database(path=db_path)
    db.conn.execute("SELECT 1"); logger.info(f"Database connection established successfully: {db.conn}")
    db.bot = bot
except (sqlite3.Error, Exception) as e:
    logger.exception(f"CRITICAL: Database initialization failed at {db_path}: {e}")
    print(f"CRITICAL: Database initialization failed at {db_path}: {e}"); raise SystemExit(f"Database failed: {e}")
logging_service = LoggingService(db)
notifier = NotificationService(bot, db)
user_manager = UserManager(db)


# --- Middleware ---
# ... (SubscriptionMiddleware без изменений) ...
class SubscriptionMiddleware:
    async def __call__(self, handler, event, data):
        # --- ВРЕМЕННОЕ ОТКЛЮЧЕНИЕ ПРОВЕРКИ ПОДПИСКИ ---
        # Эта строка немедленно передает управление дальше, игнорируя все проверки ниже.
        # Чтобы снова включить проверку, просто удалите или закомментируйте эту строку.
        return await handler(event, data)
        # --- КОНЕЦ ВРЕМЕННОГО ОТКЛЮЧЕНИЯ ---

        # Весь остальной код проверки ниже теперь не будет выполняться
        if isinstance(event, (types.Message, types.CallbackQuery)):
            user = event.from_user
            # Пропускаем проверку если юзер не определен или это бот или админ
            if not user or user.is_bot or user.id == ADMIN_ID:
                return await handler(event, data)
            user_id = user.id
            try:
                # Получаем статус пользователя в канале
                user_status = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
                allowed_statuses = ["member", "administrator", "creator"]
                # Если статус не разрешенный
                if user_status.status not in allowed_statuses:
                    user_db_data = db.get_user(user_id); name = user_db_data.get("name") if user_db_data else None
                    link = f"https://t.me/{CHANNEL_ID.lstrip('@')}" # Формируем ссылку на канал
                    text = f"{name}, рад видеть тебя. ✨ Для нашей совместной работы, пожалуйста, подпишись на <a href='{link}'>канал автора</a>. Это важно для поддержки пространства. После подписки просто нажми /start." if name else f"Рад видеть тебя. ✨ Для нашей совместной работы, пожалуйста, подпишись на <a href='{link}'>канал автора</a>. Это важно для поддержки пространства. После подписки просто нажми /start."

                    # Отвечаем в зависимости от типа события
                    if isinstance(event, types.Message):
                        await event.answer(text, disable_web_page_preview=True)
                    elif isinstance(event, types.CallbackQuery):
                        # Отвечаем на коллбэк и отправляем сообщение в чат
                        await event.answer("Пожалуйста, подпишись на канал.", show_alert=True)
                        await event.message.answer(text, disable_web_page_preview=True)
                    return # Прерываем выполнение хэндлера
            except Exception as e:
                logger.error(f"Subscription check failed for user {user_id}: {e}")
                error_text = f"Не получается проверить твою подписку на канал {CHANNEL_ID}. Убедись, пожалуйста, что ты подписана, и попробуй снова через /start."
                if isinstance(event, types.Message): await event.answer(error_text)
                elif isinstance(event, types.CallbackQuery): await event.answer("Не удается проверить подписку.", show_alert=False); await event.message.answer(error_text)
                return # Прерываем выполнение хэндлера
        # Если все проверки пройдены, передаем управление дальше
        # (Эта строка теперь недостижима из-за добавленной выше)
        return await handler(event, data)


# --- Общая функция для запроса времени ---
# Теперь импорт State сработает
async def ask_for_time(message: types.Message, state: FSMContext, prompt_text: str, next_state: State):
    """Отправляет сообщение с запросом времени и устанавливает следующее состояние."""
    await message.answer(prompt_text)
    await state.set_state(next_state)

# --- Обработчики стандартных команд ---
# ... (все обработчики make_... и register_handlers как в предыдущем ответе) ...
# ... (включая новые обработчики для напоминаний) ...
# --- /start ---
def make_start_handler(db, logger_service, user_manager):
    # ... (код start без изменений) ...
    async def wrapped_handler(message: types.Message, state: FSMContext, command: CommandObject | None = None):
        await state.clear()
        user_id = message.from_user.id
        username = message.from_user.username or ""
        args = command.args if command else ""
        await logger_service.log_action(user_id, "start_command", {"args": args})
        user_data = db.get_user(user_id)
        # Обновляем юзернейм, если он изменился или отсутствовал
        if user_data.get("username") != username: db.update_user(user_id, {"username": username})
        # Обработка реферальной ссылки
        if args and args.startswith("ref_"):
            try:
                referrer_id = int(args[4:])
                # Нельзя быть рефералом самого себя
                if referrer_id != user_id:
                    # Пытаемся добавить реферала, метод вернет True если добавлено успешно (т.е. раньше не было)
                    if db.add_referral(referrer_id, user_id):
                         referrer_data = db.get_user(referrer_id)
                         # Даем бонус рефереру, только если у него его еще нет
                         if referrer_data and not referrer_data.get("bonus_available"):
                             await user_manager.set_bonus_available(referrer_id, True)
                             ref_name = referrer_data.get("name", "Друг")
                             text = f"{ref_name}, ура! 🎉 Кто-то воспользовался твоей ссылкой! Теперь тебе доступна '💌 Подсказка Вселенной' в меню."
                             try:
                                 await bot.send_message(referrer_id, text, reply_markup=await get_main_menu(referrer_id, db))
                                 await logger_service.log_action(referrer_id, "referral_bonus_granted", {"referred_user": user_id})
                             except Exception as send_err:
                                 logger.error(f"Failed to send referral bonus message to {referrer_id}: {send_err}")
            except (ValueError, TypeError, IndexError) as ref_err:
                logger.warning(f"Invalid referral code processing '{args}' from user {user_id}: {ref_err}")
        # Проверяем, есть ли имя у пользователя
        user_name = user_data.get("name")
        if not user_name:
            # Запрашиваем имя, если его нет
            await message.answer("Здравствуй! ✨ Очень рад нашему знакомству. Подскажи, как мне лучше к тебе обращаться?",
                                 reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="Пропустить", callback_data="skip_name")]]))
            await state.set_state(UserState.waiting_for_name)
        else:
            # Приветствуем по имени и показываем меню
            await message.answer(f"{user_name}, снова рад тебя видеть! 👋 Готова поработать с картой дня или подвести итог?",
                                 reply_markup=await get_main_menu(user_id, db))
    return wrapped_handler

# --- Команда /remind ---
def make_remind_handler(db, logger_service, user_manager):
    # ... (код make_remind_handler как в предыдущем ответе) ...
    async def wrapped_handler(message: types.Message, state: FSMContext):
        user_id = message.from_user.id
        user_data = db.get_user(user_id)
        name = user_data.get("name", "Друг")
        morning_reminder = user_data.get("reminder_time")
        evening_reminder = user_data.get("reminder_time_evening")
        morning_text = f"Напоминание 'Карта дня' ✨: <b>{morning_reminder}</b> МСК" if morning_reminder else "Напоминание 'Карта дня' ✨: <b>отключено</b>"
        evening_text = f"Напоминание 'Итог дня' 🌙: <b>{evening_reminder}</b> МСК" if evening_reminder else "Напоминание 'Итог дня' 🌙: <b>отключено</b>"
        purpose_text = "⏰ Настроим ежедневные напоминания?"
        instruction_text = ("Сначала введи удобное время для <b>утреннего</b> напоминания 'Карта дня' в формате <b>ЧЧ:ММ</b> (например, <code>09:00</code>).\nИли напиши <code>выкл</code>, чтобы отключить это напоминание.\n\n"
                           f"<u>Текущие настройки:</u>\n- {morning_text}\n- {evening_text}")
        text = f"{name}, привет!\n\n{purpose_text}\n\n{instruction_text}"
        await message.answer(text, reply_markup=await get_main_menu(user_id, db)) # Показываем меню для контекста
        await state.set_state(UserState.waiting_for_morning_reminder_time) # Устанавливаем состояние
        await logger_service.log_action(user_id, "remind_command_invoked")
    return wrapped_handler

# --- Новая команда /broadcast (для теста) ---
def make_broadcast_handler(db: Database, logger_service: LoggingService):
    """Создает обработчик для команды /broadcast (ТЕСТОВЫЙ РЕЖИМ)."""
    async def wrapped_handler(message: types.Message):
        user_id = message.from_user.id
        if user_id != ADMIN_ID:
            await message.reply("Эта команда доступна только администратору.")
            return

        # Получаем текст для рассылки (все, что после /broadcast )
        broadcast_text = message.text[len("/broadcast"):].strip()
        if not broadcast_text:
            await message.reply("Пожалуйста, укажите текст для рассылки после команды.\n"
                                "Пример: `/broadcast Привет! У бота обновления!`")
            return

        # Фиксированный текст из вашего примера (можно оставить или использовать broadcast_text)
        # Замените на broadcast_text, если хотите отправлять текст из команды
        text_to_send = """Привет! Надеюсь, у вас все хорошо. ✨

Хочу поделиться новостями: я немного обновился, чтобы наша работа с картами и саморефлексией стала еще глубже и полезнее!

1) У меня новое имя – "Ресурсный помощник". Мне кажется, оно лучше отражает то, чем я могу быть для вас полезен. 😊

2) Теперь я умею составлять "Профиль пользователя" (загляните через команду /user_profile!), где бережно собираются важные моменты нашего взаимодействия. Узнайте себя немного лучше!

3) Появился уютный вечерний ритуал "🌙 Итог дня" – всего пара минут, чтобы мягко завершить день и позаботиться о себе.

Очень хочется снова пообщаться! Нажмите /start, чтобы увидеть обновленное меню и попробовать новинки.

С нетерпением жду встречи!
Ваш Ресурсный помощник ❤️"""

        # users = db.get_all_users() # <-- Закомментировано: Получение всех пользователей
        users = [457463804, 478901963, 517423026, 644771890, 683970407, 684097293, 685995409, 806894927, 834325767, 1068630660, 1123817690, 1159751971, 1264280911, 1348873495, 1664012269, 1821666039, 1853568101, 1887924167, 5741110759,6288394996, 865377684, 171507422] # <-- Добавлено: Тестирование на конкретном ID
        if not users:
            # Эта проверка становится менее актуальной, но не мешает
            await message.reply("Не удалось определить пользователя для тестовой рассылки.")
            return

        await message.reply(f"Начинаю ТЕСТОВУЮ рассылку сообщения для {len(users)} пользователя (ID: {users[0]})...") # Уточнено сообщение админу
        await logger_service.log_action(user_id, "broadcast_test_started", {"target_user_id": users[0], "text_preview": text_to_send[:50]})

        success_count = 0
        fail_count = 0
        failed_users = [] # Хотя здесь будет максимум 1

        # Цикл теперь пройдет только один раз
        for target_user_id in users:
            try:
                # Используем HTML для возможного форматирования в будущем, если понадобится
                await bot.send_message(target_user_id, text_to_send, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                success_count += 1
                # Логируем успех для каждого пользователя (опционально, может быть много логов)
                # await logger_service.log_action(ADMIN_ID, "broadcast_sent_user", {"target_user_id": target_user_id})
            except TelegramAPIError as e:
                fail_count += 1
                failed_users.append(target_user_id)
                logger.error(f"Failed to send broadcast to {target_user_id}: {e}")
                await logger_service.log_action(ADMIN_ID, "broadcast_failed_user", {"target_user_id": target_user_id, "error": str(e)})
            except Exception as e: # Ловим другие возможные ошибки
                fail_count += 1
                failed_users.append(target_user_id)
                logger.error(f"Unexpected error sending broadcast to {target_user_id}: {e}", exc_info=True)
                await logger_service.log_action(ADMIN_ID, "broadcast_failed_user", {"target_user_id": target_user_id, "error": f"Unexpected: {str(e)}"})

            # Пауза здесь не так критична, но можно оставить
            await asyncio.sleep(0.05)

        result_text = f"✅ Тестовая рассылка завершена!\nУспешно отправлено: {success_count}\nНе удалось отправить: {fail_count}"
        if failed_users:
            result_text += f"\nID пользователя с ошибкой: {failed_users[0]}"
        await message.reply(result_text)
        await logger_service.log_action(ADMIN_ID, "broadcast_test_finished", {"success": success_count, "failed": fail_count})

    return wrapped_handler

# --- Обработчик ввода УТРЕННЕГО времени ---
def make_process_morning_reminder_time_handler(db, logger_service, user_manager):
    # ... (код make_process_morning_reminder_time_handler как в предыдущем ответе) ...
     async def wrapped_handler(message: types.Message, state: FSMContext):
        user_id = message.from_user.id
        name = db.get_user(user_id).get("name", "Друг")
        input_text = message.text.strip().lower()
        morning_time_to_save = None
        if input_text == "выкл":
            morning_time_to_save = None
            await logger_service.log_action(user_id, "reminder_set_morning", {"time": "disabled"})
            await message.reply("Хорошо, утреннее напоминание 'Карта дня' отключено.")
        else:
            try:
                # Проверяем формат ЧЧ:ММ
                reminder_dt = datetime.strptime(input_text, "%H:%M")
                morning_time_to_save = reminder_dt.strftime("%H:%M")
                await logger_service.log_action(user_id, "reminder_set_morning", {"time": morning_time_to_save})
                await message.reply(f"Утреннее время <code>{morning_time_to_save}</code> принято.")
            except ValueError:
                # Если формат неверный
                await message.reply(f"{name}, не совсем понял время. 🕰️ Пожалуйста, введи время для <b>утреннего</b> напоминания в формате ЧЧ:ММ (например, <code>08:30</code>) или напиши <code>выкл</code>.")
                return # Остаемся в том же состоянии
        # Сохраняем утреннее время в state и запрашиваем вечернее
        await state.update_data(morning_time=morning_time_to_save)
        evening_prompt = "Теперь введи время для <b>вечернего</b> напоминания 'Итог дня' 🌙 (ЧЧ:ММ) или напиши <code>выкл</code>."
        await ask_for_time(message, state, evening_prompt, UserState.waiting_for_evening_reminder_time)
     return wrapped_handler

# --- Обработчик ввода ВЕЧЕРНЕГО времени ---
def make_process_evening_reminder_time_handler(db, logger_service, user_manager):
    # ... (код make_process_evening_reminder_time_handler как в предыдущем ответе) ...
     async def wrapped_handler(message: types.Message, state: FSMContext):
        user_id = message.from_user.id
        name = db.get_user(user_id).get("name", "Друг")
        input_text = message.text.strip().lower()
        evening_time_to_save = None
        state_data = await state.get_data()
        morning_time = state_data.get("morning_time") # Получаем утреннее время из state
        if input_text == "выкл":
            evening_time_to_save = None
            await logger_service.log_action(user_id, "reminder_set_evening", {"time": "disabled"})
        else:
            try:
                # Проверяем формат ЧЧ:ММ
                reminder_dt = datetime.strptime(input_text, "%H:%M")
                evening_time_to_save = reminder_dt.strftime("%H:%M")
                await logger_service.log_action(user_id, "reminder_set_evening", {"time": evening_time_to_save})
            except ValueError:
                # Если формат неверный
                await message.reply(f"{name}, не понял время. 🕰️ Пожалуйста, введи время для <b>вечернего</b> напоминания (ЧЧ:ММ) или напиши <code>выкл</code>.")
                return # Остаемся в том же состоянии
        # Сохраняем ОБА времени в базу и выходим из FSM
        try:
            await user_manager.set_reminder(user_id, morning_time, evening_time_to_save)
            await logger_service.log_action(user_id, "reminders_saved_total", {"morning_time": morning_time, "evening_time": evening_time_to_save})
            # Формируем подтверждение
            morning_confirm = f"'Карта дня' ✨: <b>{morning_time}</b> МСК" if morning_time else "'Карта дня' ✨: <b>отключено</b>"
            evening_confirm = f"'Итог дня' 🌙: <b>{evening_time_to_save}</b> МСК" if evening_time_to_save else "'Итог дня' 🌙: <b>отключено</b>"
            text = f"{name}, готово! ✅\nНапоминания установлены:\n- {morning_confirm}\n- {evening_confirm}"
            await message.answer(text, reply_markup=await get_main_menu(user_id, db))
            await state.clear() # Очищаем состояние
        except Exception as e:
            logger.error(f"Failed to save reminders for user {user_id}: {e}", exc_info=True)
            await message.answer("Ой, произошла ошибка при сохранении настроек...")
            await state.clear() # Очищаем состояние в любом случае
     return wrapped_handler

# --- Команда /remind_off ---
def make_remind_off_handler(db, logger_service, user_manager):
    # ... (код remind_off как в предыдущем ответе) ...
     async def wrapped_handler(message: types.Message, state: FSMContext):
         user_id = message.from_user.id
         # Выходим из FSM, если пользователь был в процессе установки напоминаний
         current_state = await state.get_state()
         if current_state in [UserState.waiting_for_morning_reminder_time, UserState.waiting_for_evening_reminder_time]:
             await state.clear()
         try:
             await user_manager.clear_reminders(user_id)
             await logger_service.log_action(user_id, "reminders_cleared")
             name = db.get_user(user_id).get("name", "Друг")
             text = f"{name}, я отключил <b>все</b> напоминания для тебя (утреннее и вечернее). Если захочешь включить снова, используй /remind."
             await message.answer(text, reply_markup=await get_main_menu(user_id, db))
         except Exception as e:
             logger.error(f"Failed to disable reminders for user {user_id}: {e}", exc_info=True)
             await message.answer("Ой, не получилось отключить напоминания...")
     return wrapped_handler

# --- Остальные команды ---
def make_share_handler(db, logger_service):
    # ... (код share) ...
    async def wrapped_handler(message: types.Message):
        user_id = message.from_user.id
        name = db.get_user(user_id).get("name", "Друг")
        ref_link = f"{BOT_LINK}?start=ref_{user_id}"
        text = (f"{name}, хочешь поделиться этим ботом с друзьями?\nВот твоя персональная ссылка: {ref_link}\n\n"
               f"Когда кто-нибудь перейдет по ней и начнет использовать бота, ты получишь доступ к '💌 Подсказке Вселенной' в главном меню! ✨")
        await message.answer(text, reply_markup=await get_main_menu(user_id, db))
        await logger_service.log_action(user_id, "share_command")
    return wrapped_handler

def make_name_handler(db, logger_service, user_manager):
    # ... (код name) ...
     async def wrapped_handler(message: types.Message, state: FSMContext):
         user_id = message.from_user.id
         name = db.get_user(user_id).get("name")
         text = f"Твое текущее имя: <b>{name}</b>.\nХочешь изменить?" if name else "Как тебя зовут?"
         text += "\nВведи новое имя или нажми 'Пропустить', если не хочешь указывать."
         await message.answer(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="Пропустить", callback_data="skip_name")]]))
         await state.set_state(UserState.waiting_for_name)
         await logger_service.log_action(user_id, "name_change_initiated")
     return wrapped_handler

def make_feedback_handler(db, logger_service):
    # ... (код feedback) ...
     async def wrapped_handler(message: types.Message, state: FSMContext):
         user_id = message.from_user.id
         name = db.get_user(user_id).get("name", "Друг")
         text = (f"{name}, хочешь поделиться идеей, как сделать меня лучше, или рассказать о проблеме?\nЯ внимательно читаю все сообщения! Напиши здесь все, что думаешь.")
         await message.answer(text, reply_markup=await get_main_menu(user_id, db)) # Оставляем меню
         await state.set_state(UserState.waiting_for_feedback)
         await logger_service.log_action(user_id, "feedback_initiated")
     return wrapped_handler

def make_user_profile_handler(db, logger_service):
    # ... (код user_profile без изменений) ...
     async def wrapped_handler(message: types.Message, state: FSMContext):
        await state.clear() # Очищаем состояние на всякий случай
        user_id = message.from_user.id
        name = db.get_user(user_id).get("name", "Друг")
        await logger_service.log_action(user_id, "user_profile_viewed")

        # Используем функцию построения профиля из ai_service
        profile = await build_user_profile(user_id, db)

        # Извлекаем данные из профиля с проверками
        mood = profile.get("mood", "неизвестно")
        mood_trend_list = [m for m in profile.get("mood_trend", []) if m != "unknown"]
        mood_trend = " → ".join(mood_trend_list) if mood_trend_list else "нет данных"
        themes_list = profile.get("themes", [])
        themes = ", ".join(themes_list) if themes_list and themes_list != ["не определено"] else "нет данных"

        initial_resource = profile.get("initial_resource") or "нет данных"
        final_resource = profile.get("final_resource") or "нет данных"
        recharge_method = profile.get("recharge_method") or "нет данных"

        last_reflection_date = profile.get("last_reflection_date") or "пока не было"
        reflection_count = profile.get("reflection_count", 0)

        response_count = profile.get("response_count", 0)
        days_active = profile.get("days_active", 0)
        total_cards_drawn = profile.get("total_cards_drawn", 0)

        last_updated_dt = profile.get("last_updated")
        last_updated = last_updated_dt.astimezone(TIMEZONE).strftime("%Y-%m-%d %H:%M") if isinstance(last_updated_dt, datetime) else "не обновлялся"

        text = (
             f"📊 <b>{name}, твой профиль взаимодействия:</b>\n\n"
             f"👤 <b>Состояние & Темы:</b>\n  - Настроение (последнее): {mood}\n  - Тренд настроения: {mood_trend}\n  - Ключевые темы (из карт и рефлексий): {themes}\n\n"
             f"🌿 <b>Ресурс (последняя 'Карта дня'):</b>\n  - В начале: {initial_resource}\n  - В конце: {final_resource}\n  - Способ восстановления: {recharge_method}\n\n"
             f"🌙 <b>Вечерняя Рефлексия:</b>\n  - Последний итог подведен: {last_reflection_date}\n  - Всего итогов подведено: {reflection_count}\n\n"
             f"📈 <b>Статистика Активности:</b>\n  - Ответов в диалогах с картой: {response_count}\n  - Всего карт вытянуто: {total_cards_drawn}\n  - Дней активности: {days_active}\n\n"
             f"⏱ <b>Профиль обновлен:</b> {last_updated} МСК\n\n"
             f"<i>Этот профиль помогает мне лучше понимать тебя. Он учитывает твои ответы в 'Карте дня' и 'Итогах дня'.</i>"
         )
        await message.answer(text, reply_markup=await get_main_menu(user_id, db))
     return wrapped_handler

# --- Админские команды (без изменений) ---
def make_admin_user_profile_handler(db, logger_service):
     # ... (код admin_user_profile) ...
     async def wrapped_handler(message: types.Message):
         user_id = message.from_user.id
         if user_id != ADMIN_ID: await message.answer("Эта команда доступна только администратору."); return

         args = message.text.split()
         if len(args) < 2:
             await message.answer("Укажи ID пользователя: /admin_user_profile <user_id>")
             return

         try:
             target_user_id = int(args[1])
         except ValueError:
             await message.answer("ID пользователя должен быть числом.")
             return

         user_info = db.get_user(target_user_id)
         if not user_info:
             await message.answer(f"Пользователь с ID {target_user_id} не найден в таблице users.")
             return

         profile = await build_user_profile(target_user_id, db)
         name = user_info.get("name", "N/A")
         username = user_info.get("username", "N/A")

         # Извлекаем данные из профиля с проверками
         mood = profile.get("mood", "N/A")
         mood_trend_list = [m for m in profile.get("mood_trend", []) if m != "unknown"]
         mood_trend = " → ".join(mood_trend_list) if mood_trend_list else "N/A"
         themes_list = profile.get("themes", [])
         themes = ", ".join(themes_list) if themes_list and themes_list != ["не определено"] else "N/A"

         initial_resource = profile.get("initial_resource") or "N/A"
         final_resource = profile.get("final_resource") or "N/A"
         recharge_method = profile.get("recharge_method") or "N/A"

         last_reflection_date = profile.get("last_reflection_date") or "N/A"
         reflection_count = profile.get("reflection_count", 0)

         response_count = profile.get("response_count", 0)
         days_active = profile.get("days_active", 0)
         total_cards_drawn = profile.get("total_cards_drawn", 0)

         last_updated_dt = profile.get("last_updated")
         last_updated = last_updated_dt.astimezone(TIMEZONE).strftime("%Y-%m-%d %H:%M") if isinstance(last_updated_dt, datetime) else "N/A"

         text = (
             f"👤 <b>Профиль пользователя:</b> <code>{target_user_id}</code>\n   Имя: {name}, Ник: @{username}\n\n"
             f"<b>Состояние & Темы:</b>\n  Настроение: {mood}\n  Тренд: {mood_trend}\n  Темы: {themes}\n\n"
             f"<b>Ресурс (последний 'Карта дня'):</b>\n  Начало: {initial_resource}\n  Конец: {final_resource}\n  Восстановление: {recharge_method}\n\n"
             f"<b>Вечерняя Рефлексия:</b>\n  Последний итог: {last_reflection_date}\n  Всего итогов: {reflection_count}\n\n"
             f"<b>Статистика Активности:</b>\n  Ответов (карта): {response_count}\n  Карт вытянуто: {total_cards_drawn}\n  Дней актив.: {days_active}\n\n"
             f"<b>Обновлено:</b> {last_updated} МСК"
         )
         await message.answer(text)
         await logger_service.log_action(user_id, "admin_user_profile_viewed", {"target_user_id": target_user_id})
     return wrapped_handler

def make_users_handler(db, logger_service):
    # ... (код users) ...
    async def wrapped_handler(message: types.Message):
        user_id = message.from_user.id
        if user_id != ADMIN_ID: await message.answer("Эта команда доступна только администратору."); return

        users = db.get_all_users()
        if not users:
            await message.answer("В базе данных нет пользователей.")
            return

        excluded_users = set(NO_LOGS_USERS) if NO_LOGS_USERS else set()
        filtered_users = [uid for uid in users if uid not in excluded_users]

        if not filtered_users:
            await message.answer("Нет пользователей для отображения (все исключены или список пуст).")
            return

        user_list = []
        for uid in filtered_users:
            user_data = db.get_user(uid)
            if not user_data: # На случай, если get_all_users вернул ID, которого уже нет
                logger.warning(f"User ID {uid} found by get_all_users but not found by get_user. Skipping.")
                continue

            name = user_data.get("name", "Без имени")
            username = user_data.get("username", "Нет никнейма")
            last_action_time = "Нет действий"
            last_action_timestamp_iso_or_dt = "1970-01-01T00:00:00+00:00" # Для сортировки по умолчанию

            # Получаем последнее действие для пользователя
            user_actions = db.get_actions(uid) # Предполагаем, что get_actions возвращает отсортированный список или можно отсортировать
            if user_actions:
                last_action = user_actions[-1] # Берем последнее действие
                raw_timestamp = last_action.get("timestamp")
                try:
                    last_action_dt = None
                    if isinstance(raw_timestamp, datetime): # Если уже datetime
                         # Приводим к нужной таймзоне, если есть pytz и объект aware
                         last_action_dt = raw_timestamp.astimezone(TIMEZONE) if raw_timestamp.tzinfo and pytz else (TIMEZONE.localize(raw_timestamp) if pytz else raw_timestamp)
                         last_action_timestamp_iso_or_dt = raw_timestamp # Сохраняем оригинал для сортировки
                    elif isinstance(raw_timestamp, str): # Если строка
                         last_action_dt = datetime.fromisoformat(raw_timestamp.replace('Z', '+00:00')).astimezone(TIMEZONE)
                         last_action_timestamp_iso_or_dt = raw_timestamp # Сохраняем строку для сортировки
                    else:
                         logger.warning(f"Invalid timestamp type for last action of user {uid}: {type(raw_timestamp)}")

                    if last_action_dt:
                         last_action_time = last_action_dt.strftime("%Y-%m-%d %H:%M")
                    else:
                         last_action_time = "Ошибка времени"
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error parsing last action timestamp for user {uid}: {raw_timestamp}, error: {e}")
                    last_action_time = f"Ошибка ({raw_timestamp})"
                    # Для сортировки оставляем строку или ставим дефолт
                    last_action_timestamp_iso_or_dt = raw_timestamp if isinstance(raw_timestamp, str) else "1970-01-01T00:00:00+00:00"

            user_list.append({
                "uid": uid,
                "username": username,
                "name": name,
                "last_action_time": last_action_time,
                "last_action_timestamp_iso_or_dt": last_action_timestamp_iso_or_dt
            })

        # Сортировка
        try:
            user_list.sort(
                key=lambda x: (x["last_action_timestamp_iso_or_dt"].astimezone(TIMEZONE) if isinstance(x["last_action_timestamp_iso_or_dt"], datetime) and x["last_action_timestamp_iso_or_dt"].tzinfo
                                else datetime.fromisoformat(str(x["last_action_timestamp_iso_or_dt"]).replace('Z', '+00:00')).astimezone(TIMEZONE) if isinstance(x["last_action_timestamp_iso_or_dt"], str)
                                else datetime.min.replace(tzinfo=TIMEZONE)),
                reverse=True
            )
        except (ValueError, TypeError) as sort_err:
            logger.error(f"Error sorting user list by timestamp: {sort_err}. List may be unsorted.")

        # Форматирование и отправка
        formatted_list = [f"ID: <code>{user['uid']}</code> | @{user['username']} | {user['name']} | Посл. действие: {user['last_action_time']}" for user in user_list]
        header = f"👥 <b>Список пользователей ({len(formatted_list)}):</b>\n(Отсортировано по последней активности)\n\n"
        full_text = header + "\n".join(formatted_list)
        max_len = 4000 # Лимит Telegram

        # Отправка по частям, если необходимо
        if len(full_text) > max_len:
            current_chunk = header
            for line in formatted_list:
                if len(current_chunk) + len(line) + 1 > max_len:
                    await message.answer(current_chunk)
                    current_chunk = "" # Начинаем новый чанк
                current_chunk += line + "\n"
            if current_chunk: # Отправляем остаток
                await message.answer(current_chunk)
        else:
            await message.answer(full_text)

        await logger_service.log_action(user_id, "users_command")
    return wrapped_handler

def make_logs_handler(db, logger_service):
    # ... (код logs) ...
    async def wrapped_handler(message: types.Message):
        user_id = message.from_user.id
        if user_id != ADMIN_ID: await message.answer("Эта команда доступна только администратору."); return

        args = message.text.split()
        target_date_str = None
        target_date = None

        # Определяем целевую дату
        if len(args) > 1:
            target_date_str = args[1]
            try:
                target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
            except ValueError:
                await message.answer("Неверный формат даты. Используй ГГГГ-ММ-ДД (например, 2024-12-31).")
                return
        else: # Если дата не указана, берем сегодняшнюю
            target_date = datetime.now(TIMEZONE).date()
            target_date_str = target_date.strftime("%Y-%m-%d")

        await logger_service.log_action(user_id, "logs_command", {"date": target_date_str})

        logs = db.get_actions() # Получаем ВСЕ действия
        filtered_logs = []
        excluded_users = set(NO_LOGS_USERS) if NO_LOGS_USERS else set()

        # Фильтруем по дате и исключенным пользователям
        for log in logs:
            log_timestamp_dt = None
            try:
                raw_timestamp = log.get("timestamp")
                # Универсальная обработка timestamp (datetime или строка ISO)
                if isinstance(raw_timestamp, datetime):
                     log_timestamp_dt = raw_timestamp.astimezone(TIMEZONE) if raw_timestamp.tzinfo and pytz else (TIMEZONE.localize(raw_timestamp) if pytz else raw_timestamp)
                elif isinstance(raw_timestamp, str):
                     log_timestamp_dt = datetime.fromisoformat(raw_timestamp.replace('Z', '+00:00')).astimezone(TIMEZONE)
                else:
                     logger.warning(f"Skipping log due to invalid timestamp type: {type(raw_timestamp)} in action {log.get('id')}")
                     continue

                # Сравниваем даты и проверяем исключения
                if log_timestamp_dt.date() == target_date and log.get("user_id") not in excluded_users:
                    log["parsed_datetime"] = log_timestamp_dt # Добавляем для форматирования
                    filtered_logs.append(log)

            except (ValueError, TypeError, KeyError) as e:
                logger.warning(f"Could not parse timestamp or missing data in log for admin view: {log}, error: {e}")
                continue

        if not filtered_logs:
            await message.answer(f"Логов за {target_date_str} не найдено (или все пользователи исключены).")
            return

        # Форматируем и отправляем логи
        log_lines = []
        for log in filtered_logs:
            ts_str = log["parsed_datetime"].strftime('%H:%M:%S')
            uid = log.get('user_id', 'N/A')
            action = log.get('action', 'N/A')
            details = log.get('details', {})
            details_str = ""
            # Форматируем details безопасно и кратко
            if isinstance(details, dict) and details:
                safe_details = {k: str(v)[:50] + ('...' if len(str(v)) > 50 else '') for k, v in details.items()} # Ограничиваем длину значения
                details_str = ", ".join([f"{k}={v}" for k, v in safe_details.items()])
                details_str = f" ({details_str[:100]}{'...' if len(details_str) > 100 else ''})" # Ограничиваем общую длину
            elif isinstance(details, str): # На случай, если details - строка
                details_str = f" (Details: {details[:100]}{'...' if len(details) > 100 else ''})"

            log_lines.append(f"{ts_str} U:{uid} A:{action}{details_str}")

        header = f"📜 <b>Логи за {target_date_str} ({len(log_lines)} записей):</b>\n\n"
        full_text = header + "\n".join(log_lines)
        max_len = 4000

        # Отправка по частям
        if len(full_text) > max_len:
            current_chunk = header
            for line in log_lines:
                if len(current_chunk) + len(line) + 1 > max_len:
                    await message.answer(current_chunk)
                    current_chunk = "" # Начинаем новый чанк
                current_chunk += line + "\n"
            if current_chunk: # Отправляем остаток
                await message.answer(current_chunk)
        else:
            await message.answer(full_text)

    return wrapped_handler

# --- Обработчики ввода имени ---
def make_process_name_handler(db, logger_service, user_manager):
    # ... (код process_name) ...
     async def wrapped_handler(message: types.Message, state: FSMContext):
         user_id = message.from_user.id
         name = message.text.strip()
         if not name: await message.answer("Имя не может быть пустым..."); return
         if len(name) > 50: await message.answer("Слишком длинное имя..."); return
         # Проверяем, не совпадает ли имя с текстом кнопок
         reserved_names = ["✨ Карта дня", "💌 Подсказка Вселенной", "🌙 Итог дня"]
         if name in reserved_names:
             await message.answer(f"Имя '{name}' использовать нельзя, оно совпадает с кнопкой меню.")
             return
         # Сохраняем имя
         await user_manager.set_name(user_id, name)
         await logger_service.log_action(user_id, "set_name", {"name": name})
         await message.answer(f"Приятно познакомиться, {name}! 😊\nТеперь можешь выбрать действие в меню.", reply_markup=await get_main_menu(user_id, db))
         await state.clear()
     return wrapped_handler

def make_process_skip_name_handler(db, logger_service, user_manager):
    # ... (код skip_name) ...
     async def wrapped_handler(callback: types.CallbackQuery, state: FSMContext):
         user_id = callback.from_user.id
         await user_manager.set_name(user_id, "") # Сохраняем пустое имя
         await logger_service.log_action(user_id, "skip_name")
         try:
             # Убираем инлайн кнопку
             await callback.message.edit_reply_markup(reply_markup=None)
         except Exception as e:
             logger.warning(f"Could not edit message on skip_name for user {user_id}: {e}")
         # Отвечаем и показываем главное меню
         await callback.message.answer("Хорошо, буду обращаться к тебе без имени.\nВыбери действие в меню.", reply_markup=await get_main_menu(user_id, db))
         await state.clear()
         await callback.answer() # Отвечаем на коллбэк
     return wrapped_handler

# --- Обработчики ввода фидбека ---
def make_process_feedback_handler(db, logger_service):
    # ... (код process_feedback) ...
      async def wrapped_handler(message: types.Message, state: FSMContext):
          user_id = message.from_user.id
          feedback_text = message.text.strip()
          if not feedback_text: await message.answer("Кажется, ты ничего не написала..."); return
          user_data = db.get_user(user_id)
          name = user_data.get("name", "Аноним") # Используем 'Аноним', если имя не установлено
          username = user_data.get("username", "N/A")
          timestamp_iso = datetime.now(TIMEZONE).isoformat()
          try:
              # Сохраняем фидбек в БД
              with db.conn:
                  db.conn.execute("INSERT INTO feedback (user_id, name, feedback, timestamp) VALUES (?, ?, ?, ?)",
                                   (user_id, name, feedback_text, timestamp_iso))
              await logger_service.log_action(user_id, "feedback_submitted", {"feedback_length": len(feedback_text)})
              await message.answer(f"{name}, спасибо за твой отзыв! 🙏", reply_markup=await get_main_menu(user_id, db)) # Показываем главное меню

              # Отправляем уведомление админу
              try:
                  admin_notify_text = (f"📝 Новый фидбек от:\nID: <code>{user_id}</code>\nИмя: {name}\nНик: @{username}\n\n<b>Текст:</b>\n{feedback_text}")
                  # Ограничиваем длину сообщения для Telegram
                  await bot.send_message(ADMIN_ID, admin_notify_text[:4090])
              except Exception as admin_err:
                  logger.error(f"Failed to send feedback notification to admin: {admin_err}")

              await state.clear() # Выходим из состояния ожидания фидбека
          except sqlite3.Error as db_err:
              logger.error(f"Failed to save feedback from user {user_id} to DB: {db_err}", exc_info=True)
              await message.answer("Ой, не получилось сохранить твой отзыв...", reply_markup=await get_main_menu(user_id, db))
              await state.clear() # Выходим из состояния даже при ошибке
      return wrapped_handler

# --- Обработчик бонуса (ИЗМЕНЕНО) ---
def make_bonus_request_handler(db, logger_service, user_manager):
     """Обработчик для кнопки 'Подсказка Вселенной'. (ИЗМЕНЕНО)"""
     async def wrapped_handler(message: types.Message):
         user_id = message.from_user.id
         user_data = db.get_user(user_id)
         name = user_data.get("name", "Друг")

         # Проверяем, доступен ли бонус
         if not user_data.get("bonus_available"):
             text = f"{name}, эта подсказка пока не доступна. Поделись своей реферальной ссылкой (/share) с другом, чтобы ее получить! ✨"
             await message.answer(text, reply_markup=await get_main_menu(user_id, db))
             return # Выходим, если бонус недоступен

         # Выбираем случайную подсказку
         advice = random.choice(UNIVERSE_ADVICE)
         text = f"{name}, вот послание Вселенной для тебя:\n\n<i>{advice}</i>" # Используем HTML для курсива

         await message.answer(text, reply_markup=await get_main_menu(user_id, db))
         await logger_service.log_action(user_id, "bonus_request_used", {"advice_preview": advice[:50]})

         # --- ИЗМЕНЕНИЕ: Убираем сброс бонуса ---
         # Следующие две строки удалены или закомментированы:
         # await user_manager.set_bonus_available(user_id, False)
         # await logger_service.log_action(user_id, "bonus_disabled_after_use")
         # --- КОНЕЦ ИЗМЕНЕНИЯ ---

     return wrapped_handler

# --- Регистрация всех обработчиков (ОБНОВЛЕНО) ---
def register_handlers(dp: Dispatcher, db: Database, logger_service: LoggingService, user_manager: UserManager):
    logger.info("Registering handlers...")
    # Создаем частичные функции
    start_handler = make_start_handler(db, logger_service, user_manager)
    share_handler = make_share_handler(db, logger_service)
    remind_handler = make_remind_handler(db, logger_service, user_manager) # <-- Используем новый
    remind_off_handler = make_remind_off_handler(db, logger_service, user_manager) # <-- Используем новый
    process_morning_reminder_time_handler = make_process_morning_reminder_time_handler(db, logger_service, user_manager) # <-- Новый
    process_evening_reminder_time_handler = make_process_evening_reminder_time_handler(db, logger_service, user_manager) # <-- Новый
    name_handler = make_name_handler(db, logger_service, user_manager)
    process_name_handler = make_process_name_handler(db, logger_service, user_manager)
    process_skip_name_handler = make_process_skip_name_handler(db, logger_service, user_manager)
    feedback_handler = make_feedback_handler(db, logger_service)
    process_feedback_handler = make_process_feedback_handler(db, logger_service)
    user_profile_handler = make_user_profile_handler(db, logger_service)
    bonus_request_handler = make_bonus_request_handler(db, logger_service, user_manager) # Используем ИЗМЕНЕННЫЙ обработчик
    users_handler = make_users_handler(db, logger_service)
    logs_handler = make_logs_handler(db, logger_service)
    admin_user_profile_handler = make_admin_user_profile_handler(db, logger_service)
    broadcast_handler = make_broadcast_handler(db, logger_service)

    # --- Регистрация команд ---
    dp.message.register(start_handler, Command("start"), StateFilter("*"))
    dp.message.register(share_handler, Command("share"), StateFilter("*"))
    dp.message.register(remind_handler, Command("remind"), StateFilter("*"))
    dp.message.register(remind_off_handler, Command("remind_off"), StateFilter("*"))
    dp.message.register(name_handler, Command("name"), StateFilter("*"))
    dp.message.register(feedback_handler, Command("feedback"), StateFilter("*"))
    dp.message.register(user_profile_handler, Command("user_profile"), StateFilter("*"))
    # Админские команды
    dp.message.register(users_handler, Command("users"), StateFilter("*"))
    dp.message.register(logs_handler, Command("logs"), StateFilter("*"))
    dp.message.register(admin_user_profile_handler, Command("admin_user_profile"), StateFilter("*"))
    dp.message.register(broadcast_handler, Command("broadcast"), StateFilter("*"))

    # --- Регистрация текстовых кнопок меню ---
    dp.message.register(bonus_request_handler, F.text == "💌 Подсказка Вселенной", StateFilter("*")) # Используем ИЗМЕНЕННЫЙ обработчик
    dp.message.register(partial(handle_card_request, db=db, logger_service=logger_service), F.text == "✨ Карта дня", StateFilter("*"))
    # Регистрируем роутер для Вечерней рефлексии (вместо прямого хендлера)
    # dp.include_router(reflection_router) # Используем роутер из evening_reflection.py
    dp.message.register(partial(start_evening_reflection, db=db, logger_service=logger_service), F.text == "🌙 Итог дня", StateFilter("*"))
    
    # --- Регистрация состояний FSM ---
    dp.message.register(process_name_handler, UserState.waiting_for_name)
    dp.callback_query.register(process_skip_name_handler, F.data == "skip_name", UserState.waiting_for_name)
    dp.message.register(process_feedback_handler, UserState.waiting_for_feedback)

    # --- Регистрация состояний напоминаний (НОВОЕ) ---
    dp.message.register(process_morning_reminder_time_handler, UserState.waiting_for_morning_reminder_time)
    dp.message.register(process_evening_reminder_time_handler, UserState.waiting_for_evening_reminder_time)
    # Старый обработчик удален:
    # dp.message.register(process_reminder_time_handler, UserState.waiting_for_reminder_time)

    # --- Флоу "Карты Дня" (без изменений) ---
    dp.callback_query.register(partial(process_initial_resource_callback, db=db, logger_service=logging_service), UserState.waiting_for_initial_resource, F.data.startswith("resource_"))
    dp.callback_query.register(partial(process_request_type_callback, db=db, logger_service=logging_service), UserState.waiting_for_request_type_choice, F.data.startswith("request_type_"))
    dp.message.register(partial(process_request_text, db=db, logger_service=logging_service), UserState.waiting_for_request_text_input)
    dp.message.register(partial(process_initial_response, db=db, logger_service=logging_service), UserState.waiting_for_initial_response)
    dp.callback_query.register(partial(process_exploration_choice_callback, db=db, logger_service=logging_service), UserState.waiting_for_exploration_choice, F.data.startswith("explore_"))
    dp.message.register(partial(process_first_grok_response, db=db, logger_service=logging_service), UserState.waiting_for_first_grok_response)
    dp.message.register(partial(process_second_grok_response, db=db, logger_service=logging_service), UserState.waiting_for_second_grok_response)
    dp.message.register(partial(process_third_grok_response, db=db, logger_service=logging_service), UserState.waiting_for_third_grok_response)
    dp.callback_query.register(partial(process_final_resource_callback, db=db, logger_service=logging_service), UserState.waiting_for_final_resource, F.data.startswith("resource_"))
    dp.message.register(partial(process_recharge_method, db=db, logger_service=logging_service), UserState.waiting_for_recharge_method)
    dp.callback_query.register(partial(process_card_feedback, db=db, logger_service=logging_service), F.data.startswith("feedback_v2_"), StateFilter("*"))

    # --- Флоу "Итог дня" (обработчики внутри reflection_router) ---
    # Регистрация хендлеров для Итога Дня больше не нужна здесь, т.к. они в роутере
    dp.message.register(partial(process_good_moments, db=db, logger_service=logger_service), UserState.waiting_for_good_moments)
    dp.message.register(partial(process_gratitude, db=db, logger_service=logger_service), UserState.waiting_for_gratitude)
    dp.message.register(partial(process_hard_moments, db=db, logger_service=logger_service), UserState.waiting_for_hard_moments)

    # --- Обработчики некорректных вводов ---
    async def handle_text_when_waiting_callback(message: types.Message, state: FSMContext):
        current_state = await state.get_state()
        logger.warning(f"User {message.from_user.id} sent text '{message.text}' while in state {current_state}, expected callback.")
        await message.reply("Пожалуйста, используй кнопки для этого шага.")

    async def handle_callback_when_waiting_text(callback: types.CallbackQuery, state: FSMContext):
        current_state = await state.get_state()
        logger.warning(f"User {callback.from_user.id} sent callback '{callback.data}' while in state {current_state}, expected text.")
        await callback.answer("Пожалуйста, отправь ответ текстом...", show_alert=True)

    # Регистрация общих обработчиков ошибок ввода
    # Ожидаем коллбэк, получили текст
    dp.message.register(handle_text_when_waiting_callback, StateFilter(
        UserState.waiting_for_initial_resource,
        UserState.waiting_for_request_type_choice,
        UserState.waiting_for_exploration_choice,
        UserState.waiting_for_final_resource
    ))
    # Ожидаем текст, получили коллбэк
    dp.callback_query.register(handle_callback_when_waiting_text, StateFilter(
        UserState.waiting_for_name, # Может прийти skip_name, но ожидался текст имени
        UserState.waiting_for_request_text_input,
        UserState.waiting_for_initial_response,
        UserState.waiting_for_first_grok_response,
        UserState.waiting_for_second_grok_response,
        UserState.waiting_for_third_grok_response,
        UserState.waiting_for_recharge_method,
        UserState.waiting_for_feedback,
        UserState.waiting_for_morning_reminder_time,
        UserState.waiting_for_evening_reminder_time,
        # Состояния Итога Дня (если они ожидают текст)
        UserState.waiting_for_good_moments,
        UserState.waiting_for_gratitude,
        UserState.waiting_for_hard_moments
    ))


    # --- Обработчики неизвестных команд/сообщений (В КОНЦЕ!) ---
    @dp.message(StateFilter("*")) # Обработка неизвестных сообщений В ЛЮБОМ СОСТОЯНИИ
    async def handle_unknown_message_state(message: types.Message, state: FSMContext):
        logger.warning(f"Unknown message '{message.text}' from user {message.from_user.id} in state {await state.get_state()}")
        await message.reply("Ой, кажется, я не ожидал этого сейчас... Попробуй вернуться через /start или используй команду из меню.")

    @dp.message() # Обработка неизвестных сообщений БЕЗ СОСТОЯНИЯ
    async def handle_unknown_message_no_state(message: types.Message):
        logger.warning(f"Unknown message '{message.text}' from user {message.from_user.id} with no state.")
        # Можно не отвечать или дать общую подсказку
        # await message.reply("Извини, не понял твой запрос... Используй команды из меню.")

    @dp.callback_query(StateFilter("*")) # Обработка неизвестных коллбэков В ЛЮБОМ СОСТОЯНИИ
    async def handle_unknown_callback_state(callback: types.CallbackQuery, state: FSMContext):
        logger.warning(f"Unknown callback '{callback.data}' from user {callback.from_user.id} in state {await state.get_state()}")
        await callback.answer("Это действие сейчас недоступно.", show_alert=True)

    @dp.callback_query() # Обработка неизвестных коллбэков БЕЗ СОСТОЯНИЯ
    async def handle_unknown_callback_no_state(callback: types.CallbackQuery):
        logger.warning(f"Unknown callback '{callback.data}' from user {callback.from_user.id} with no state.")
        await callback.answer("Неизвестное действие.", show_alert=True)

    logger.info("Handlers registered successfully.")


# --- Запуск бота ---
async def main():
    # ... (код main() без изменений) ...
    logger.info("Starting bot...")
    commands = [
        types.BotCommand(command="start", description="🔄 Перезагрузка"),
        types.BotCommand(command="name", description="👩🏼 Указать имя"),
        types.BotCommand(command="remind", description="⏰ Настроить напоминания"),
        types.BotCommand(command="remind_off", description="🔕 Выключить все напоминания"),
        types.BotCommand(command="share", description="🎁 Поделиться с другом"),
        types.BotCommand(command="feedback", description="✉️ Оставить отзыв / Идею"),
        types.BotCommand(command="user_profile", description="📊 Мой профиль")
    ]
    # Добавляем админские команды, если они есть
    #if ADMIN_ID:
    #     commands.extend([
    #         types.BotCommand(command="users", description="👥 Адм: Список юзеров"),
    #         types.BotCommand(command="logs", description="📜 Адм: Логи за дату"),
    #         types.BotCommand(command="admin_user_profile", description="👤 Адм: Профиль юзера")
    #     ])

    try:
        await bot.set_my_commands(commands)
        logger.info("Bot commands set successfully.")
    except Exception as e:
        logger.error(f"Failed to set bot commands: {e}")

    # Передаем зависимости в диспетчер
    dp["db"] = db
    dp["logger_service"] = logging_service
    dp["user_manager"] = user_manager

    # Регистрируем обработчики
    register_handlers(dp, db, logging_service, user_manager)

    # Запускаем фоновую задачу проверки напоминаний
    reminder_task = asyncio.create_task(notifier.check_reminders())
    logger.info("Reminder check task scheduled.")

    logger.info("Starting polling...")
    print("Bot is starting polling...")
    try:
        # Запускаем поллинг
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logger.critical(f"Polling failed: {e}", exc_info=True)
        print(f"CRITICAL: Polling failed: {e}")
    finally:
        # Корректное завершение работы
        logger.info("Stopping bot...")
        print("Bot is stopping...")
        reminder_task.cancel()
        try:
            await reminder_task # Ожидаем завершения задачи
        except asyncio.CancelledError:
            logger.info("Reminder task cancelled successfully.")
        # Закрываем соединение с БД
        if db and db.conn:
            try:
                db.close() # Используем метод close() класса Database
            except Exception as db_close_err:
                logger.error(f"Error closing database connection: {db_close_err}")
        # Очистка сессии бота (aiogram обычно делает это сам при остановке поллинга)
        logger.info("Bot session cleanup (handled by aiogram).")
        print("Bot stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped manually.")
    except Exception as e:
        # Логируем критическую ошибку на верхнем уровне
        logger.critical(f"Critical error in main execution: {e}", exc_info=True)
        print(f"CRITICAL error in main execution: {e}")
