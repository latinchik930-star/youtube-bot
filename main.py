from datetime import datetime, timedelta
import requests
import telebot
from telebot import types

TELEGRAM_TOKEN = "9246241192:AAHwAr8DWkcBfEQZK4nS2sBYCuA2Zo0r4hk"
YOUTUBE_API_KEY = "AIzaSyBNPFQlvdqH9WXQ9Cwb3SKpJAaUirBa288"

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
      "key": YOUTUBE_API_KEY,
  }

  response = requests.get(search_url, params=search_params)
  search_data = response.json()

  if "items" not in search_data:
    return []

  new_items = [
      item
      for item in search_data["items"]
      if item["id"]["videoId"] not in seen_ids
  ]

  if not new_items:
    return []

  video_ids = [item["id"]["videoId"] for item in new_items]

  stats_url = "https://www.googleapis.com/youtube/v3/videos"
  stats_params = {
      "part": "statistics,snippet",
      "id": ",".join(video_ids),
      "key": YOUTUBE_API_KEY,
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

      found_videos.append(
          f"🎬 {title}\n🔗 https://www.youtube.com/watch?v={video_id}\n👀"
          f" Просмотров: {view_count}"
      )

      if len(found_videos) >= 3:
        break

  return found_videos


@bot.message_handler(commands=["start"])
def send_welcome(message):
  user_id = message.from_user.id
  user_sessions[user_id] = {"query": "", "seen": set()}

  bot.reply_to(
      message,
      "Привет! Напиши ключевое слово для поиска. Бот ищет свежие непопулярные"
      " видео с разных каналов и поддерживает рулетку!",
  )


@bot.message_handler(func=lambda message: True)
def search_videos(message):
  user_id = message.from_user.id
  query = message.text.strip()

  if user_id not in user_sessions:
    user_sessions[user_id] = {"query": query, "seen": set()}

  bot.send_message(message.chat.id, f"🎰 Ищу видео по запросу: '{query}'...")

  videos = fetch_videos_batch(query, user_id)

  markup = types.InlineKeyboardMarkup()
  btn = types.InlineKeyboardButton(
      "🔄 Крутить еще", callback_data="roll_next"
  )
  markup.add(btn)

  if videos:
    result_text = f"🎯 Результаты по запросу '{query}':\n\n" + "\n\n".join(videos)
    bot.send_message(message.chat.id, result_text, reply_markup=markup)
  else:
    bot.send_message(
        message.chat.id,
        "По этому запросу не нашлось новых видео с просмотрами меньше 500."
        " Попробуй другой запрос или чуть позже!",
    )


@bot.callback_query_handler(func=lambda call: call.data == "roll_next")
def callback_roll(call):
  user_id = call.from_user.id

  if user_id not in user_sessions or not user_sessions[user_id]["query"]:
    bot.answer_callback_query(
        call.id, "Сначала отправь текстовый запрос в чат!", show_alert=True
    )
    return

  query = user_sessions[user_id]["query"]
  bot.answer_callback_query(call.id, "Крутим дальше...")

  videos = fetch_videos_batch(query, user_id)

  markup = types.InlineKeyboardMarkup()
  btn = types.InlineKeyboardButton(
      "🔄 Крутить еще", callback_data="roll_next"
  )
  markup.add(btn)

  if videos:
    result_text = f"🎰 Новая порция по запросу '{query}':\n\n" + "\n\n".join(
        videos
    )
    bot.send_message(call.message.chat.id, result_text, reply_markup=markup)
  else:
    bot.answer_callback_query(
        call.id,
        "Больше уникальных видео по этому запросу нет!",
        show_alert=True,
    )


print("Бот запущен...")
bot.polling(none_stop=True)
