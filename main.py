import os
import threading
from datetime import datetime, timedelta
from flask import Flask
import requests
import telebot
from telebot import types

# Инициализация Flask для открытия порта на Render
app = Flask(__name__)


@app.route("/")
def home():
  return "Bot is running!"


# Твои ключи и настройки
TELEGRAM_TOKEN = (
    "9246241192:AAHwAr8DWkcBfEQZK4nS2sBYCuA2Zo0r4hk"  # noqa: E501
)
YUTE_API_KEY = "AIzaSyBNPFQ1vdqH9WXQ9Cwb3SKpJAAuirBa288"  # noqa: E501

bot = telebot.TeleBot(TELEGRAM_TOKEN)
user_sessions = {}


def fetch_videos_batch(query, user_id):
  if user_id not in user_sessions:
    user_sessions[user_id] = {"query": query, "seen": set()}

  if user_sessions[user_id]["query"] != query:
    user_sessions[user_id] = {"query": query, "seen": set()}

  seen_ids = user_sessions[user_id]["seen"]

  now = datetime.utcnow()
  start_date = (now - timedelta(days=60)).isoformat() + "Z"

  search_url = "https://www.googleapis.com/youtube/v3/search"
  search_params = {
      "part": "snippet",
      "q": query,
      "type": "video",
      "publishedAfter": start_date,
      "order": "date",
      "maxResults": 30,
      "key": YUTE_API_KEY,
  }

  response = requests.get(search_url, params=search_params)
  search_data = response.json()

  if "items" not in search_data:
    return []

  new_items = []
  for item in search_data["items"]:
    if item["id"]["videoId"] not in seen_ids:
      new_items.append(item)

  if not new_items:
    return []

  video_ids = [item["id"]["videoId"] for item in new_items]

  stats_url = "https://www.googleapis.com/youtube/v3/videos"
  stats_params = {
      "part": "statistics,snippet",
      "id": ",".join(video_ids),
      "key": YUTE_API_KEY,
  }

  stats_response = requests.get(stats_url, params=stats_params)
  stats_data = stats_response.json()

  found_videos = []
  seen_channels = set()

  for item in stats_data.get("items", []):
    view_count = int(item["statistics"].get("viewCount", 0))

    if view_count < 500:
      channel_id = item["snippet"]["channelId"]

      if channel_id in seen_channels:
        continue

      video_id = item["id"]
      title = item["snippet"]["title"]

      seen_channels.add(channel_id)
      seen_ids.add(video_id)

      found_videos.append((video_id, title, view_count))

  return found_videos


# Здесь можно добавить обработчики твоего бота (handlers), если они были ниже


# Функция для запуска самого телеграм-бота
def run_bot():
  bot.infinity_polling(none_stop=True)


if __name__ == "__main__":
  # Запускаем телеграм-бота в отдельном фоновом потоке
  bot_thread = threading.Thread(target=run_bot)
  bot_thread.daemon = True
  bot_thread.start()

  # Получаем порт от Render (по умолчанию 5000 для локального теста)
  port = int(os.environ.get("PORT", 5000))
  # Запускаем Flask-сервер, чтобы Render видел открытый порт
  app.run(host="0.0.0.0", port=port)
  
