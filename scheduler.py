# scheduler.py
import schedule
import time
from datetime import datetime, timedelta
import os
import json
from config import MARATHONS

def send_post(bot, marathon_id, day, post_id, chat_id, content_folder):
    folder = f"content/{content_folder}/day{day}/post{post_id}"
    if os.path.exists(folder):
        # Текст
        if os.path.exists(f"{folder}/text.txt"):
            with open(f"{folder}/text.txt", "r", encoding="utf-8") as f:
                bot.send_message(chat_id=chat_id, text=f.read(), parse_mode="HTML")

        # Изображение
        if os.path.exists(f"{folder}/image.jpg"):
            with open(f"{folder}/image.jpg", "rb") as f:
                bot.send_photo(chat_id=chat_id, photo=f)

        # Голосовое сообщение
        if os.path.exists(f"{folder}/voice.ogg"):
            with open(f"{folder}/voice.ogg", "rb") as f:
                bot.send_voice(chat_id=chat_id, voice=f)

        # Видео
        if os.path.exists(f"{folder}/video.mp4"):
            with open(f"{folder}/video.mp4", "rb") as f:
                bot.send_video(chat_id=chat_id, video=f)

        # PDF-файл
        if os.path.exists(f"{folder}/document.pdf"):
            with open(f"{folder}/document.pdf", "rb") as f:
                bot.send_document(chat_id=chat_id, document=f)

        # Опрос
        if os.path.exists(f"{folder}/poll.json"):
            with open(f"{folder}/poll.json", "r", encoding="utf-8") as f:
                poll_data = json.load(f)
                bot.send_poll(
                    chat_id=chat_id,
                    question=poll_data["question"],
                    options=poll_data["options"],
                    is_anonymous=poll_data["is_anonymous"]
                )

def schedule_posts(bot):
    for marathon_id, settings in MARATHONS.items():
        chat_id = settings["chat_id"]
        start_date = datetime.strptime(settings["start_date"], "%Y-%m-%d")
        duration = settings["duration_days"]
        repeat_interval = settings["repeat_interval"]
        content_folder = settings["content_folder"]
        schedule_file = f"schedules/{settings['schedule_file']}"

        # Загружаем расписание из JSON
        if os.path.exists(schedule_file):
            with open(schedule_file, "r", encoding="utf-8") as f:
                posts_schedule = json.load(f)
        else:
            print(f"Расписание для {marathon_id} не найдено!")
            continue

        # Планируем посты для текущего и будущих циклов
        current_date = start_date
        cycle = 0
        while True:  # Бесконечный цикл для повторяющихся марафонов
            for post in posts_schedule:
                if post["day"] <= duration:  # Проверяем, что день входит в длительность марафона
                    post_date = current_date + timedelta(days=post["day"] - 1)
                    schedule_time = post_date.strftime("%Y-%m-%d") + " " + post["time"]
                    schedule.every().day.at(post["time"]).do(
                        send_post,
                        bot=bot,
                        marathon_id=marathon_id,
                        day=post["day"],
                        post_id=post["post_id"],
                        chat_id=chat_id,
                        content_folder=content_folder
                    ).tag(f"{marathon_id}_cycle{cycle}_day{post['day']}_post{post['post_id']}")
            # Сдвигаем дату для следующего цикла
            if repeat_interval:
                current_date += timedelta(days=repeat_interval)
                cycle += 1
            else:
                break

    # Запускаем цикл проверки расписания
    while True:
        schedule.run_pending()
        time.sleep(60)  # Проверяем каждую минуту