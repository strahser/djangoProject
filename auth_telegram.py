import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoProject.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from djangoProject.settings import TELEGRAM_API_ID, TELEGRAM_API_HASH, BASE_DIR
from telethon.sync import TelegramClient

SESSION_DIR = os.path.join(BASE_DIR, 'TelegramParser', 'sessions')
os.makedirs(SESSION_DIR, exist_ok=True)
session_path = os.path.join(SESSION_DIR, 'default')

print(f"API ID: {TELEGRAM_API_ID}")
print(f"Session: {session_path}")
print()

client = TelegramClient(session_path, TELEGRAM_API_ID, TELEGRAM_API_HASH)
client.start()

print()
print("=== Авторизация успешна! ===")

entity = client.get_me()
print(f"Вы вошли как: {entity.first_name} (ID: {entity.id})")

client.disconnect()
print("Сессия сохранена. Теперь парсер будет работать без запроса кода.")
