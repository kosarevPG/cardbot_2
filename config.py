import pytz
import os 

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = "@TopPsyGame"
BOT_LINK = "t.me/choose_a_card_bot"
TIMEZONE = pytz.timezone("Europe/Moscow")
ADMIN_ID = 6682555021 

# --- Google Sheets ---
GOOGLE_SHEET_NAME = "MarathonContent"

# --- YandexGPT ---
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID") 
YANDEX_GPT_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

GROK_API_KEY = os.getenv("GROK_API_KEY")
GROK_API_URL = "https://api.x.ai/v1/chat/completions"

NO_CARD_LIMIT_USERS = [6682555021, 392141189, 239719200]
NO_LOGS_USERS = [6682555021, 392141189, 239719200, 7494824111,171507422,138192985]
DATA_DIR = "/data"

# Список советов Вселенной
UNIVERSE_ADVICE = [
    "<b>💌 Ты — источник силы.</b> Всё, что тебе нужно, уже внутри. Просто доверься себе и сделай первый шаг.",
    "<b>💌 Дыши глубже.</b> В каждом вдохе — возможность начать заново.",
    "<b>💌 Маленькие шаги ведут к большим вершинам.</b> Начни с того, что можешь сделать прямо сейчас.",
    "<b>💌 Вселенная всегда на твоей стороне.</b> Даже если сейчас это не очевидно.",
    "<b>💌 Отпусти контроль.</b> Иногда лучшее решение — довериться течению.",
    "<b>💌 Ты сильнее, чем думаешь.</b> Вспомни, сколько ты уже преодолела.",
    "<b>💌 Слушай своё сердце.</b> Оно знает путь, даже если разум сомневается.",
    "<b>💌 Каждый момент — это подарок.</b> Найди в нём что-то ценное.",
    "<b>💌 Ты не одна.</b> Вселенная поддерживает тебя через людей, знаки и случайности.",
    "<b>💌 Будь мягче к себе.</b> Ты делаешь лучшее, на что способна прямо сейчас.",
    "<b>💌 Всё временно.</b> И трудности, и радости — это лишь часть пути.",
    "<b>💌 Задавай вопросы.</b> Ответы приходят, когда ты готова их услышать.",
    "<b>💌 Ты достойна всего хорошего.</b> Просто потому, что ты есть.",
    "<b>💌 Ищи свет.</b> Даже в темноте всегда есть искры надежды.",
    "<b>💌 Твоя интуиция — твой компас.</b> Доверяй ей, она не подведёт.",
    "<b>💌 Отдых — это сила.</b> Позволь себе остановиться и восстановиться.",
    "<b>💌 Ты растешь.</b> Каждый опыт — это шаг к твоей лучшей версии.",
    "<b>💌 Будь здесь и сейчас.</b> Всё, что нужно, уже с тобой в этом моменте.",
    "<b>💌 Смелость — твоя природа.</b> Сделай то, что пугает, и увидишь, как открываются новые горизонты.",
    "<b>💌 Ресурсы не заканчиваются, они перетекают.</b> Подключись к потоку жизни и доверься её ритму."
]


# Настройки обучающих курсов
TUTORIALS = {
    "mak_tutorial": {
        "name": "Что такое МАК? (Обучение)",
    }
}

# Настройки марафонов
MARATHONS = {
    "internal_conflicts": {
        "name": "Психосоматика внутренних конфликтов",
        "chat_id": "your_internal_conflicts_chat_id_here",  # Замените на ID канала
        "start_date": "2025-04-10",  # Начало марафона
        "duration_days": 7,  # Длительность марафона (7 дней)
        "repeat_interval": 30,  # Повторять каждые 30 дней
        "content_folder": "internal_conflicts",
        "schedule_file": "internal_conflicts.json"
    },
    "excess_weight": {
        "name": "Психосоматика лишнего веса: что скрывают кг?",
        "chat_id": "your_excess_weight_chat_id_here",
        "start_date": "2025-04-17",
        "duration_days": 4,
        "repeat_interval": 30,
        "content_folder": "excess_weight",
        "schedule_file": "excess_weight.json"
    },
    "relationships": {
        "name": "Психосоматика отношений: узлы, которые оставляют люди",
        "chat_id": "your_relationships_chat_id_here",
        "start_date": "2025-04-24",
        "duration_days": 6,
        "repeat_interval": 30,
        "content_folder": "relationships",
        "schedule_file": "relationships.json"
    },
    "self_worth": {
        "name": "Психосоматика самоценности: разреши себе быть",
        "chat_id": "your_self_worth_chat_id_here",
        "start_date": "2025-05-01",
        "duration_days": 5,
        "repeat_interval": 30,
        "content_folder": "self_worth",
        "schedule_file": "self_worth.json"
    },
    "success": {
        "name": "Психосоматика успеха: от сомнений к победам",
        "chat_id": "your_success_chat_id_here",
        "start_date": "2025-05-08",
        "duration_days": 7,
        "repeat_interval": 30,
        "content_folder": "success",
        "schedule_file": "success.json"
    },
    "health": {
        "name": "Психосоматика здоровья: ключи к исцелению",
        "chat_id": "your_health_chat_id_here",
        "start_date": "2025-05-15",
        "duration_days": 6,
        "repeat_interval": 30,
        "content_folder": "health",
        "schedule_file": "health.json"
    },
    "sexuality": {
        "name": "Психосоматика сексуальности: путь к наслаждению",
        "chat_id": "your_sexuality_chat_id_here",
        "start_date": "2025-05-22",
        "duration_days": 5,
        "repeat_interval": 30,
        "content_folder": "sexuality",
        "schedule_file": "sexuality.json"
    },
    "money": {
        "name": "Психосоматика денег: от блоков к потокам",
        "chat_id": "your_money_chat_id_here",
        "start_date": "2025-05-29",
        "duration_days": 7,
        "repeat_interval": 30,
        "content_folder": "money",
        "schedule_file": "money.json"
    }
}
