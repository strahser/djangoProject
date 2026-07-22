import sys
import threading
import traceback
from django.contrib import admin, messages
from django.http import JsonResponse
from django.shortcuts import redirect
from loguru import logger

from .models import TelegramChannel, ParseLog


def _log(msg):
    print(f"[TGParser] {msg}", flush=True)
    sys.stdout.flush()


def _run_parse_in_thread(channel_username, log_id=None):
    from .parser import parse_channel

    def _target():
        try:
            _log(f"Старт парсинга: {channel_username}")
            result = parse_channel(channel_username, incremental=True)
            _log(f"Парсинг завершён: {channel_username} -> {result}")
        except Exception as e:
            _log(f"ОШИБКА парсинга {channel_username}: {e}")
            _log(traceback.format_exc())
            try:
                if log_id:
                    from django.utils import timezone
                    log = ParseLog.objects.get(pk=log_id)
                    log.status = 'error'
                    log.error_message = str(e)
                    log.finished_at = timezone.now()
                    log.save()
            except Exception:
                pass

    thread = threading.Thread(target=_target, daemon=True, name=f"TGParser-{channel_username}")
    thread.start()
    return thread


def fetch_channel_data(request, channel_id):
    from django.utils import timezone

    channel = TelegramChannel.objects.get(pk=channel_id)
    log = ParseLog.objects.create(
        channel=channel, operation='api', status='running'
    )

    _log(f"Кнопка 'Получить данные': {channel.name} (@{channel.username})")
    _run_parse_in_thread(channel.username, log_id=log.pk)

    messages.success(
        request,
        f'Парсинг канала "{channel.name}" запущен (ID лога: {log.pk}). '
        f'Обновите страницу логов через несколько секунд.'
    )

    return redirect(request.META.get('HTTP_REFERER', admin.site.name))


def parse_status(request):
    """JSON endpoint: статус последних логов парсинга."""
    logs = ParseLog.objects.select_related('channel').order_by('-started_at')[:5]
    data = []
    for log in logs:
        data.append({
            'id': log.pk,
            'channel': log.channel.name if log.channel else 'N/A',
            'status': log.status,
            'operation': log.operation,
            'messages_found': log.messages_found,
            'messages_saved': log.messages_saved,
            'messages_skipped': log.messages_skipped,
            'error': log.error_message[:200] if log.error_message else '',
            'started_at': log.started_at.strftime('%H:%M:%S') if log.started_at else '',
            'finished_at': log.finished_at.strftime('%H:%M:%S') if log.finished_at else None,
        })
    return JsonResponse({'logs': data})
