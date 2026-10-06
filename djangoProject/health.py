"""Liveness/readiness probe (блок 33): GET /healthz/ без логина.

Проверяет только доступность БД (SELECT 1): для перезапуска/мониторинга,
а не диагностику.
"""
from django.db import connection
from django.http import JsonResponse


def healthz(request):
    try:
        with connection.cursor() as cur:
            cur.execute('SELECT 1')
            cur.fetchone()
    except Exception as e:
        return JsonResponse(
            {'status': 'fail', 'db': str(e)[:200]}, status=503)
    return JsonResponse({'status': 'ok', 'db': 'ok'})
