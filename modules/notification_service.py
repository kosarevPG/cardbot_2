# код/notification_service.py

import asyncio
from datetime import datetime
from config import TIMEZONE
from strings import (
    MORNING_REMINDER_MESSAGE_WITH_NAME, MORNING_REMINDER_MESSAGE_NO_NAME,
    EVENING_REMINDER_MESSAGE_WITH_NAME, EVENING_REMINDER_MESSAGE_NO_NAME,
    DEFAULT_NAME
)
import logging
# Импортируем функцию для получения меню
from modules.card_of_the_day import get_main_menu

class NotificationService:
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        # Убрал basicConfig отсюда, лучше настраивать в main.py
        self.logger = logging.getLogger(__name__) # Используем именованный логгер

    async def check_reminders(self):
        """Проверяет и отправляет утренние и вечерние напоминания."""
        while True:
            try:
                now = datetime.now(TIMEZONE)
                current_time_str = now.strftime("%H:%M")
                today = now.date()
                reminders_data = self.db.get_reminder_times() # Получаем словарь {user_id: {'morning': t1, 'evening': t2}}

                for user_id, times in reminders_data.items():
                    user_data = self.db.get_user(user_id) # Получаем имя
                    name = user_data.get("name", "")

                    # Проверка утреннего напоминания (Карта Дня)
                    morning_time = times.get('morning')
                    if morning_time == current_time_str and self.db.is_card_available(user_id, today):
                        text = MORNING_REMINDER_MESSAGE_WITH_NAME.format(name=name) if name else MORNING_REMINDER_MESSAGE_NO_NAME
                        try:
                            # Отправляем с клавиатурой, чтобы сразу можно было нажать
                            await self.bot.send_message(user_id, text, reply_markup=await get_main_menu(user_id, self.db))
                            self.logger.info(f"Morning reminder sent to user {user_id} at {now}")
                            # Возможно, стоит добавить лог действия через logger_service?
                        except Exception as e:
                            self.logger.error(f"Failed to send MORNING reminder to user {user_id}: {e}")

                    # Проверка вечернего напоминания (Итог Дня)
                    evening_time = times.get('evening')
                    # Дополнительно проверяем, не было ли уже рефлексии сегодня (опционально, но полезно)
                    # today_str = today.strftime('%Y-%m-%d')
                    # reflection_exists = await self.db.check_evening_reflection_exists(user_id, today_str) # Нужен новый метод в DB
                    # if evening_time == current_time_str and not reflection_exists:
                    if evening_time == current_time_str: # Пока без проверки на существование
                        text = EVENING_REMINDER_MESSAGE_WITH_NAME.format(name=name) if name else EVENING_REMINDER_MESSAGE_NO_NAME
                        try:
                            # Отправляем с клавиатурой
                            await self.bot.send_message(user_id, text, reply_markup=await get_main_menu(user_id, self.db))
                            self.logger.info(f"Evening reminder sent to user {user_id} at {now}")
                        except Exception as e:
                            self.logger.error(f"Failed to send EVENING reminder to user {user_id}: {e}")

            except Exception as loop_err:
                self.logger.error(f"Error in reminder check loop: {loop_err}", exc_info=True)
                # Ждем дольше в случае серьезной ошибки в цикле
                await asyncio.sleep(300) # Ждем 5 минут перед повторной попыткой
                continue # Переходим к следующей итерации цикла

            await asyncio.sleep(60) # Проверяем каждую минуту

    # ... (существующий метод send_broadcast) ...

    async def send_broadcast(self, broadcast_data):
        # Логируем входные данные
        logging.info(f"Starting broadcast with datetime: {broadcast_data['datetime']}, recipients: {broadcast_data['recipients']}")

        while True:
            now = datetime.now(TIMEZONE)
            logging.info(f"Current time: {now}, Target time: {broadcast_data['datetime']}")

            if now >= broadcast_data["datetime"]:
                recipients = self.db.get_all_users() if broadcast_data["recipients"] == "all" else broadcast_data["recipients"]
                for user_id in recipients:
                    name = self.db.get_user(user_id)["name"]
                    text = f"{name}, {broadcast_data['text']}" if name else broadcast_data["text"]
                    try:
                        await self.bot.send_message(user_id, text)
                        logging.info(f"Broadcast sent to user {user_id} at {now}")
                    except Exception as e:
                        logging.error(f"Failed to send broadcast to user {user_id}: {e}")
                break  # Выходим из цикла после отправки
            else:
                # Ждём до следующей проверки (например, 60 секунд)
                time_to_wait = (broadcast_data["datetime"] - now).total_seconds()
                wait_seconds = min(time_to_wait, 60)  # Ждём не больше 60 секунд за раз
                logging.info(f"Waiting {wait_seconds} seconds until broadcast time")
                await asyncio.sleep(wait_seconds)
