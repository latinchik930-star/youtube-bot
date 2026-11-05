import os
import threading
from datetime import datetime, timedelta
from flask import Flask
import requests
import telebot

# Инициализация Flask для удержания открытого порта на Render
app = Flask(__name__)


@app.route("/")
def home():
  return "Bot is running!"


# Твои ключи и настройки
TELEGRAM_TOKEN = "9246241192:AAHwAr8DWkcBfEQZK4nS2sBYCuA2Zo0r4hk"
YUTE_API_KEY = "AIzaSyBNPFQ1vdqH9WXQ9Cwb3SKpJAAuirBa288"

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

  all_items = search_data["items"]
  
  # Фильтруем те, что уже показывали
  new_items = [item for item in all_items if item["id"]["videoId"] not in seen_ids]

  # Если всё из текущей выдачи уже видели — сбрасываем память (бесконечная рулетка)
  if not new_items:
    seen_ids.clear()
    new_items = all_items

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
  all_parsed_videos = []

  for item in stats_data.get("items", []):
    view_count = int(item["statistics"].get("viewCount", 0))
    channel_id = item["snippet"]["channelId"]
    video_id = item["id"]
    title = item["snippet"]["title"]

    all_parsed_videos.append((video_id, title, view_count, channel_id))

    # Пытаемся найти строго меньше 500 с уникальных каналов
    if view_count < 500:
      if channel_id in seen_channels:
        continue
      seen_channels.add(channel_id)
      seen_ids.add(video_id)
      found_videos.append((video_id, title, view_count))

  # Запасной вариант: если под жесткий фильтр < 500 ничего не попало вообще, 
  # берем топ-4 самых малопросматриваемых из того, что нашлось, как на твоих скриншотах
  if not found_videos and all_parsed_videos:
    all_parsed_videos.sort(key=lambda x: x[2])  # Сортируем по просмотрам
    for video_id, title, view_count, channel_id in all_parsed_videos[:4]:
      seen_ids.add(video_id)
      found_videos.append((video_id, title, view_count))

  return found_videos


# Обработчик команды /start
@bot.message_handler(commands=["start"])
def send_welcome(message):
  bot.reply_to(
      message,
      "Привет! Напиши мне ключевое слово, и я найду свежие видео с YouTube.",
  )


# Обработчик текстовых запросов (поиск видео в точности как на скринах)
@bot.message_handler(func=lambda message: True)
def handle_query(message):
  query = message.text
  bot.reply_to(message, f"Ищу свежие непопулярные видео по запросу: {query}...")

  videos = fetch_videos_batch(query, message.from_user.id)

  if not videos:
    bot.send_message(
        message.chat.id,
        "К сожалению, по этому запросу ничего не удалось найти.",
    )
    return

  # Формируем красивый ответ списком, как на твоих скриншотах
  response_lines = ["Вот свежие непопулярные видео:\n"]
  for video_id, title, view_count in videos:
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    response_lines.append(f"{video_url} (Просмотров: {view_count})")

  bot.send_message(message.chat.id, "\n".join(response_lines))


# Функция запуска бота в отдельном потоке
def run_bot():
  try:
    bot.infinity_polling(none_stop=True, interval=0, timeout=20)
  except Exception as e:
    print(f"Bot polling error: {e}")


if __name__ == "__main__":
  bot_thread = threading.Thread(target=run_bot)
  bot_thread.daemon = True
  bot_thread.start()

  port = int(os.environ.get("PORT", 5000))
  app.run(host="0.0.0.0", port=port)
  
