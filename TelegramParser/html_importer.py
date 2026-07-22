import os
import re
from datetime import datetime
from bs4 import BeautifulSoup
from loguru import logger
from django.utils import timezone

from .models import TelegramMessage, TelegramChannel, ParseLog, Tag, Category
from .importance import calculate_importance
from .tag_categories import get_category_for_tag


def extract_hashtags(text_div):
    tags = []
    if not text_div:
        return tags
    for a in text_div.find_all('a', onclick=True):
        onclick = a.get('onclick', '')
        match = re.search(r'ShowHashtag\("(\w+)"\)', onclick)
        if match:
            tags.append(match.group(1))
    return tags


def extract_links(text_div):
    links = []
    if not text_div:
        return links
    for a in text_div.find_all('a', href=True):
        onclick = a.get('onclick', '')
        if 'ShowHashtag' in onclick:
            continue
        href = a['href']
        if href and not href.startswith('#') and not href.startswith('javascript:'):
            links.append(href)
    return links


def parse_reactions(body):
    reactions = {}
    reactions_span = body.select_one('span.reactions')
    if not reactions_span:
        return reactions, 0
    for r in reactions_span.select('span.reaction'):
        emoji_el = r.select_one('span.emoji')
        count_el = r.select_one('span.count')
        if emoji_el and count_el:
            emoji = emoji_el.get_text(strip=True)
            count = int(count_el.get_text(strip=True))
            reactions[emoji] = count
    total = sum(reactions.values())
    return reactions, total


def parse_datetime_from_title(title_attr):
    clean = re.sub(r'\s*UTC[+-]\d{2}:\d{2}$', '', title_attr)
    try:
        dt = datetime.strptime(clean, '%d.%m.%Y %H:%M:%S')
        return timezone.make_aware(dt)
    except ValueError:
        return None


def ensure_tag(tag_name):
    tag, _ = Tag.objects.get_or_create(
        name=tag_name,
        defaults={'category': ensure_category(get_category_for_tag(tag_name))}
    )
    return tag


def ensure_category(category_name):
    slug = category_name.lower().replace(' ', '-').replace('и', '')
    category, _ = Category.objects.get_or_create(
        slug=slug,
        defaults={'name': category_name}
    )
    return category


def link_tags_to_message(message):
    tag_objects = []
    for tag_name in message.tags:
        tag_objects.append(ensure_tag(tag_name))
    if tag_objects:
        message.tag_objects.set(tag_objects)


def import_html_file(html_path, channel_name=None, channel_username=None):
    logger.info(f"Начало импорта: {html_path}")

    with open(html_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')

    header = soup.select_one('div.page_header div.text.bold')
    if header:
        detected_name = header.get_text(strip=True)
        if detected_name:
            channel_name = detected_name

    if not channel_name:
        channel_name = 'Unknown'

    channel_username = channel_username or channel_name.lower().replace(' ', '_')
    channel, _ = TelegramChannel.objects.get_or_create(
        username=channel_username,
        defaults={'name': channel_name}
    )

    history = soup.select_one('div.history')
    if not history:
        logger.warning(f"Не найден div.history в {html_path}")
        return 0, 0, 0

    messages_found = 0
    messages_saved = 0
    messages_skipped = 0
    last_author = None

    for msg in history.find_all('div', class_='message', recursive=False):
        classes = msg.get('class', [])
        msg_id_attr = msg.get('id', '')

        if 'service' in classes:
            continue

        telegram_id = None
        id_match = re.search(r'message(\d+)', msg_id_attr)
        if id_match:
            telegram_id = int(id_match.group(1))

        if not telegram_id:
            continue

        messages_found += 1

        if TelegramMessage.objects.filter(telegram_id=telegram_id).exists():
            messages_skipped += 1
            continue

        body = msg.select_one('div.body')
        if not body:
            continue

        date_div = body.select_one('div.pull_right.date.details')
        full_datetime = None
        if date_div:
            title = date_div.get('title', '')
            full_datetime = parse_datetime_from_title(title)

        from_name = body.select_one('div.from_name')
        if from_name:
            last_author = from_name.get_text(strip=True)
        author = last_author or ''

        text_div = body.select_one('div.text')
        text = text_div.get_text(strip=True) if text_div else ''
        html_text = str(text_div) if text_div else ''

        tags = extract_hashtags(text_div)
        links = extract_links(text_div)
        reactions, total_reactions = parse_reactions(body)

        has_media = body.select_one('div.media_wrap') is not None
        media_type = ''
        if has_media:
            if body.select_one('a.photo_wrap'):
                media_type = 'photo'
            elif body.select_one('div.media_video'):
                media_type = 'video'
            else:
                media_type = 'other'

        importance = calculate_importance(total_reactions, tags, links)

        msg_obj = TelegramMessage.objects.create(
            telegram_id=telegram_id,
            channel=channel,
            channel_name=channel_name,
            author=author,
            text=text,
            html_text=html_text,
            date=full_datetime or timezone.now(),
            tags=tags,
            links=links,
            reactions=reactions,
            total_reactions=total_reactions,
            importance=importance,
            has_media=has_media,
            media_type=media_type,
            source='html',
        )
        link_tags_to_message(msg_obj)
        messages_saved += 1

    logger.info(
        f"Импорт завершён: найдено={messages_found}, "
        f"сохранено={messages_saved}, пропущено={messages_skipped}"
    )

    return messages_found, messages_saved, messages_skipped


def import_html_directory(export_dir, channel_name=None, channel_username=None):
    html_files = sorted([
        os.path.join(export_dir, f)
        for f in os.listdir(export_dir)
        if re.match(r'messages\d*\.html$', f)
    ])

    if not html_files:
        logger.error(f"Не найдены messages*.html в {export_dir}")
        return 0, 0, 0

    total_found = total_saved = total_skipped = 0
    for html_file in html_files:
        found, saved, skipped = import_html_file(html_file, channel_name, channel_username)
        total_found += found
        total_saved += saved
        total_skipped += skipped
        logger.info(f"  {os.path.basename(html_file)}: +{saved} новых из {found}")

    logger.info(
        f"Итого: найдено={total_found}, сохранено={total_saved}, "
        f"пропущено={total_skipped}"
    )
    return total_found, total_saved, total_skipped
