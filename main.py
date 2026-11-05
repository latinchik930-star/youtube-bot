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
    return [], False

  all_items = search_data["items"]
  
  # Оставляем только то, что пользователь еще не видел в этой сессии
  new_items = [item for item in all_items if item["id"]["videoId"] not in seen_ids]

  # Если новые ролики закончились — сбрасываем память (бесконечный цикл рулетки)
  is_reset = False
  if not new_items:
    seen_ids.clear()
    new_items = all_items
    is_reset = True

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

    # Основной фильтр
    if view_count < 500:
      if channel_id in seen_channels:
        continue
      seen_channels.add(channel_id)
      seen_ids.add(video_id)
      found_videos.append((video_id, title, view_count))

  # Умный фоллбек: если под < 500 ничего не нашлось, берем топ-3 самых малопросматриваемых из выдачи
  if not found_videos and all_parsed_videos:
    all_parsed_videos.sort(key=lambda x: x[2]) # Сортируем по просмотрам (по возрастанию)
    for video_id, title, view_count, channel_id in all_parsed_videos[:3]:
      seen_ids.add(video_id)
      found_videos.append((video_id, title, view_count))

  return found_videos, is_reset


# Обработчик команды /start
@bot.message_handler(commands=["start"])
def send_welcome(message):
  bot.reply_to(
      message,
      "Привет! Напиши мне ключевое слово, и я найду свежие видео с YouTube.",
  )


# Обработчик текстовых запросов (поиск видео)
@bot.message_handler(func=lambda message: True)
def handle_query(message):
  query = message.text
  bot.reply_to(message, f"Ищу свежие видео по запросу: «{query}»...")

  videos, is_reset = fetch_videos_batch(query, message.from_user.id)

  if not videos:
    bot.send_message(
        message.chat.id,
        "К сожалению, по этому запросу совсем ничего не удалось найти.",
    )
    return

  if is_reset:
    bot.send_message(
        message.chat.id, 
        "🔄 Свежие уникальные варианты в выдаче закончились. Начинаем новый круг по тем же роликам!"
    )

  for video_id, title, view_count in videos:
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    # Подсказка, если ролик выведен как запасной вариант (когда меньше 500 нет вообще)
    status_text = f"👀 Просмотров: {view_count}"
    if view_count >= 500:
      status_text += " (меньше 500 нет, это самый малопросмотровый из свежих)"

    bot.send_message(
        message.chat.id,
        f"📺 **{title}**\n{status_text}\n🔗 {video_url}",
        parse_mode="Markdown",
    )


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
  
