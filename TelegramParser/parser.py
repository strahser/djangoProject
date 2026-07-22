import re
import sys
from loguru import logger
from django.utils import timezone

from .models import TelegramMessage, TelegramChannel, ParseLog, Tag
from .importance import calculate_importance
from .telegram_client import get_client
from .html_importer import ensure_tag, link_tags_to_message


def _log(msg):
    print(f"[TGParser] {msg}", flush=True)
    sys.stdout.flush()


def extract_tags_from_entities(message):
    tags = []
    if message.entities:
        for entity in message.entities:
            if hasattr(entity, 'hashtag'):
                tag = message.message[entity.offset + 1:entity.offset + entity.length]
                tags.append(tag)
    if not tags:
        for match in re.finditer(r'#(\w+)', message.message or ''):
            tags.append(match.group(1))
    return tags


def extract_links_from_entities(message):
    links = []
    if message.entities:
        for entity in message.entities:
            if hasattr(entity, 'url') and entity.url:
                links.append(entity.url)
            elif hasattr(entity, 'hashtag'):
                continue
    if not links:
        for match in re.finditer(r'https?://[^\s<>"]+', message.message or ''):
            links.append(match.group(0))
    return links


def parse_message(msg, channel_name):
    telegram_id = msg.id
    author = ''
    if msg.sender:
        if hasattr(msg.sender, 'first_name'):
            author = f"{msg.sender.first_name or ''} {msg.sender.last_name or ''}".strip()
        elif hasattr(msg.sender, 'title'):
            author = msg.sender.title

    text = msg.message or ''
    tags = extract_tags_from_entities(msg)
    links = extract_links_from_entities(msg)

    reactions = {}
    total_reactions = 0
    if msg.reactions:
        for reaction in msg.reactions.results:
            emoji = reaction.reaction.emoticon if hasattr(reaction.reaction, 'emoticon') else str(reaction.reaction)
            count = reaction.count
            reactions[emoji] = count
            total_reactions += count

    has_media = msg.media is not None
    media_type = ''
    if has_media:
        media_class = type(msg.media).__name__
        media_map = {
            'MessageMediaPhoto': 'photo',
            'MessageMediaDocument': 'document',
            'MessageMediaVideo': 'video',
            'MessageMediaWebPage': 'webpage',
        }
        media_type = media_map.get(media_class, 'other')

    importance = calculate_importance(total_reactions, tags, links)

    return {
        'telegram_id': telegram_id,
        'channel_name': channel_name,
        'author': author,
        'text': text,
        'html_text': '',
        'date': msg.date,
        'tags': tags,
        'links': links,
        'reactions': reactions,
        'total_reactions': total_reactions,
        'importance': importance,
        'has_media': has_media,
        'media_type': media_type,
        'is_pinned': False,
        'source': 'api',
    }


def get_max_telegram_id(channel_obj):
    last_msg = TelegramMessage.objects.filter(
        channel=channel_obj
    ).order_by('-telegram_id').first()
    return last_msg.telegram_id if last_msg else 0


def parse_channel(channel_username, api_id=None, api_hash=None,
                   limit=None, incremental=True):
    from djangoProject.settings import TELEGRAM_API_ID, TELEGRAM_API_HASH

    api_id = api_id or TELEGRAM_API_ID
    api_hash = api_hash or TELEGRAM_API_HASH

    channel_username = channel_username.lstrip('@')

    channel_obj, _ = TelegramChannel.objects.get_or_create(
        username=channel_username,
        defaults={'name': channel_username}
    )

    log = ParseLog.objects.create(channel=channel_obj, operation='api', status='running')
    _log(f"Старт: {channel_username}, log_id={log.pk}")

    client = get_client(api_id, api_hash)
    try:
        client.start()
        _log(f"Клиент подключён: {channel_username}")

        entity = client.get_entity(channel_username)
        channel_name = getattr(entity, 'title', channel_username)
        channel_obj.channel_id = entity.id
        channel_obj.save(update_fields=['channel_id'])

        messages_found = 0
        messages_saved = 0
        messages_skipped = 0

        kwargs = {}
        if limit:
            kwargs['limit'] = limit

        if incremental:
            max_id = get_max_telegram_id(channel_obj)
            if max_id > 0:
                kwargs['min_id'] = max_id
                _log(f"Инкрементальный: сообщения > {max_id}")

        _log(f"Итерация сообщений: {channel_username}")
        for msg in client.iter_messages(entity, **kwargs):
            messages_found += 1

            if TelegramMessage.objects.filter(telegram_id=msg.id).exists():
                messages_skipped += 1
                continue

            data = parse_message(msg, channel_name)
            data['channel'] = channel_obj
            msg_obj = TelegramMessage.objects.create(**data)

            if data['tags']:
                link_tags_to_message(msg_obj)

            messages_saved += 1

            if messages_found % 50 == 0:
                _log(f"Прогресс {channel_username}: "
                     f"найдено={messages_found}, сохранено={messages_saved}")

        channel_obj.last_parsed = timezone.now()
        channel_obj.save(update_fields=['last_parsed'])

        log.messages_found = messages_found
        log.messages_saved = messages_saved
        log.messages_skipped = messages_skipped
        log.status = 'done'
        log.finished_at = timezone.now()
        log.save()

        _log(f"Завершено {channel_username}: "
             f"найдено={messages_found}, сохранено={messages_saved}, "
             f"пропущено={messages_skipped}")

        return messages_found, messages_saved, messages_skipped

    except Exception as e:
        log.status = 'error'
        log.error_message = str(e)
        log.finished_at = timezone.now()
        log.save()
        _log(f"ОШИБКА {channel_username}: {e}")
        raise
    finally:
        client.disconnect()
