import logging
from datetime import datetime
from config import TIMEZONE

class LoggingService:
    def __init__(self, db):
        self.db = db
        logging.basicConfig(level=logging.INFO)

    async def log_action(self, user_id, action, details=None):
        chat = await self.db.bot.get_chat(user_id)
        username = chat.username or ""
        name = self.db.get_user(user_id)["name"]
        timestamp = datetime.now(TIMEZONE).isoformat()
        self.db.save_action(user_id, username, name, action, details or {}, timestamp)
        logging.info(f"User {user_id}: {action}, details: {details}")

    def get_logs_for_today(self):
        today = datetime.now(TIMEZONE).date()
        logs = self.db.get_actions()
        return [log for log in logs if datetime.fromisoformat(log["timestamp"]).astimezone(TIMEZONE).date() == today]
