import re
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from loguru import logger

from TelegramParser.models import TelegramMessage, Tag, Category
from TelegramParser.html_importer import ensure_tag, link_tags_to_message


def extract_hashtags_from_html(html_text):
    tags = []
    if not html_text:
        return tags
    soup = BeautifulSoup(html_text, 'html.parser')
    for a in soup.find_all('a', onclick=True):
        onclick = a.get('onclick', '')
        match = re.search(r'ShowHashtag\("(\w+)"\)', onclick)
        if match:
            tags.append(match.group(1))
    return tags


class Command(BaseCommand):
    help = 'Извлечь теги из html_text и присвоить теги/категории сообщениям'

    def handle(self, *args, **options):
        messages = TelegramMessage.objects.all()
        total = messages.count()
        self.stdout.write(f"Всего сообщений: {total}")

        updated = 0
        tags_extracted = 0
        for msg in messages.iterator():
            raw_tags = msg.tags
            if not raw_tags and msg.html_text:
                raw_tags = extract_hashtags_from_html(msg.html_text)
                if raw_tags:
                    msg.tags = raw_tags
                    msg.save(update_fields=['tags'])
                    tags_extracted += 1

            if raw_tags:
                link_tags_to_message(msg)
                updated += 1
                if updated % 100 == 0:
                    self.stdout.write(f"  Обработано: {updated}/{total}")

        self.stdout.write(self.style.SUCCESS(
            f"Готово! Тегов извлечено из HTML: {tags_extracted}, "
            f"Сообщений с тегами: {updated}"
        ))

        self.stdout.write(f"\nСозданные категории:")
        for cat in Category.objects.all():
            count = cat.tag_set.count()
            msg_count = TelegramMessage.objects.filter(tag_objects__category=cat).distinct().count()
            self.stdout.write(f"  {cat.name}: {count} тегов, {msg_count} сообщений")

        self.stdout.write(f"\nВсего тегов: {Tag.objects.count()}")
        self.stdout.write(f"Всего категорий: {Category.objects.count()}")
