import os
import threading
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

  search_url = "https://www.googleapis.com/youtube/v3/search"
  search_params = {
      "part": "snippet",
      "q": query,
      "type": "video",
      "order": "date",
      "maxResults": 30,
      "key": YUTE_API_KEY,
  }

  response = requests.get(search_url, params=search_params)
  search_data = response.json()

  # Выводим ответ от YouTube в логи Render для диагностики
  print("YouTube API Response:", search_data)

  if "items" not in search_data or not search_data["items"]:
    return []

  all_items = search_data["items"]
  new_items = [item for item in all_items if item["id"]["videoId"] not in seen_ids]

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
  print("YouTube Stats Response:", stats_data)

  found_videos = []
  seen_channels = set()
  all_parsed_videos = []

  for item in stats_data.get("items", []):
    view_count = int(item["statistics"].get("viewCount", 0))
    channel_id = item["snippet"]["channelId"]
    video_id = item["id"]
    title = item["snippet"]["title"]

    all_parsed_videos.append((video_id, title, view_count, channel_id))

    if view_count < 500:
      if channel_id in seen_channels:
        continue
      seen_channels.add(channel_id)
      seen_ids.add(video_id)
      found_videos.append((video_id, title, view_count))

  if not found_videos and all_parsed_videos:
    all_parsed_videos.sort(key=lambda x: x[2])
    for video_id, title, view_count, channel_id in all_parsed_videos[:4]:
      seen_ids.add(video_id)
      found_videos.append((video_id, title, view_count))

  return found_videos
  
