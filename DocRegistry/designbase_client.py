"""HTTP-клиент к DesignBase API — движку валидации (M1 DOC-3, канон §2 шаг 2).

DesignBase запускается отдельно: uvicorn designbase.api.main:app --port 8010.
Адрес — settings.DESIGNBASE_URL. В тестах подменяется mock'ом.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from django.conf import settings


class DesignBaseUnreachable(Exception):
    pass


def _base() -> str:
    return getattr(settings, 'DESIGNBASE_URL', 'http://127.0.0.1:8010').rstrip('/')


def call(path: str, method: str = 'GET', payload: dict | None = None,
         timeout: int = 60) -> dict:
    """GET/POST к DesignBase, возврат dict. При недоступности — DesignBaseUnreachable."""
    url = _base() + path
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    elif method == 'GET' and payload is None:
        pass
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        raise DesignBaseUnreachable(f'{method} {url}: {type(e).__name__}: {e}')


def get(path: str, params: dict | None = None, timeout: int = 60) -> dict:
    if params:
        path += '?' + urllib.parse.urlencode(params)
    return call(path, 'GET', None, timeout)


def post(path: str, payload: dict, timeout: int = 120) -> dict:
    return call(path, 'POST', payload, timeout)
