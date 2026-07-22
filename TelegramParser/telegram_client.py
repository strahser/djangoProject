import os
from djangoProject.settings import BASE_DIR

SESSION_DIR = os.path.join(BASE_DIR, 'TelegramParser', 'sessions')


def get_client(api_id, api_hash, session_name='default'):
    from telethon.sync import TelegramClient

    os.makedirs(SESSION_DIR, exist_ok=True)
    session_path = os.path.join(SESSION_DIR, session_name)
    return TelegramClient(session_path, api_id, api_hash)
