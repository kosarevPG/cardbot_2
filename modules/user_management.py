# код/user_management.py
from aiogram.fsm.state import State, StatesGroup
import logging

logger = logging.getLogger(__name__)

class UserState(StatesGroup):
    # Стандартные состояния
    waiting_for_name = State()
    # waiting_for_reminder_time = State() # Старое состояние - больше не используем
    waiting_for_feedback = State()

    # --- Новые состояния для напоминаний ---
    waiting_for_morning_reminder_time = State()
    waiting_for_evening_reminder_time = State()
    # ------------------------------------

    # --- Флоу Карты Дня ---
    waiting_for_initial_resource = State()
    waiting_for_request_type_choice = State()
    waiting_for_request_text_input = State()
    waiting_for_initial_response = State()
    waiting_for_exploration_choice = State()
    waiting_for_first_grok_response = State()
    waiting_for_second_grok_response = State()
    waiting_for_third_grok_response = State()
    waiting_for_final_resource = State()
    waiting_for_recharge_method = State()

    # --- Состояния для Итога Дня ---
    waiting_for_good_moments = State()
    waiting_for_gratitude = State()
    waiting_for_hard_moments = State()


class UserManager:
    # --- Код UserManager остается БЕЗ ИЗМЕНЕНИЙ ---
    def __init__(self, db):
        self.db = db

    async def set_name(self, user_id, name):
        user_data = self.db.get_user(user_id)
        if not user_data: logger.warning(f"UserManager: User {user_id} not found when trying to set name...")
        self.db.update_user(user_id, {"name": name})

    async def set_reminder(self, user_id, morning_time, evening_time): # Уже принимает оба времени
        """Устанавливает утреннее и вечернее время напоминания."""
        user_data = self.db.get_user(user_id)
        if not user_data: logger.warning(f"UserManager: User {user_id} not found when trying to set reminder.")
        self.db.update_user(user_id, {
            "reminder_time": morning_time, # Может быть None
            "reminder_time_evening": evening_time # Может быть None
        })

    async def clear_reminders(self, user_id):
        """Сбрасывает оба времени напоминания."""
        user_data = self.db.get_user(user_id)
        if not user_data: logger.warning(f"UserManager: User {user_id} not found when trying to clear reminders.")
        self.db.update_user(user_id, {"reminder_time": None, "reminder_time_evening": None})

    async def set_bonus_available(self, user_id, value):
        user_data = self.db.get_user(user_id)
        if not user_data: logger.warning(f"UserManager: User {user_id} not found when trying to set bonus.")
        self.db.update_user(user_id, {"bonus_available": value})
