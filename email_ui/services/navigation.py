"""Блок 25: навигация и сортировка списка писем (вынесено из views.py 1:1)."""

from django.shortcuts import redirect
from django.urls import reverse


ALLOWED_SORT_FIELDS = ['sender', 'receiver', 'subject', 'email_stamp', 'project_site__name', 'contractor__name']


def _sanitize_next_url(next_url):
    """Ensure 'next' always points to a full page, not a partial/ URL."""
    from django.http import QueryDict
    if not next_url:
        return reverse('email_ui:inbox_default')
    # Защита от open-redirect: разрешаем только локальные пути.
    if not next_url.startswith('/'):
        return reverse('email_ui:inbox_default')
    if '/partial/' in next_url:
        try:
            folder = 'inbox'
            qd = QueryDict('')
            if '?' in next_url:
                qs = next_url.split('?', 1)[1]
                qd = QueryDict(qs)
                folder = qd.get('folder', 'inbox')
            url = reverse('email_ui:inbox', args=[folder])
            qd_copy = qd.copy()
            for key in ('sort', 'order', 'folder'):
                qd_copy.pop(key, None)
            qs2 = qd_copy.urlencode()
            if qs2:
                url += '?' + qs2
            return url
        except Exception:
            return reverse('email_ui:inbox_default')
    return next_url


def _clean_query_string(request, remove_params=None):
    """Remove specified params from query string and return URL-encoded string.

    page/_infinite убираем всегда: ссылки «догрузить ещё» и сортировки строятся
    из текущего query string, и без чистки они накапливали собственные
    параметры (page=2&page=3&…), из-за чего список бесконечно грузил одну и
    ту же страницу дублями.

    folder убираем тоже: шаблоны сами добавляют &folder={{ folder }}, иначе в
    ссылке получалось folder=inbox&folder=inbox.
    """
    if remove_params is None:
        remove_params = ['sort', 'order', 'page', '_infinite', 'folder']
    params = request.GET.copy()
    for key in remove_params:
        params.pop(key, None)
    return params.urlencode()


def _build_back_url(request, folder='inbox'):
    """Build a full-page back URL for email list, avoiding /partial/ paths."""
    qs = _clean_query_string(request)
    url = reverse('email_ui:inbox', args=[folder])
    if qs:
        url += '?' + qs
    return url


def apply_sorting(queryset, request):
    sort_field = request.GET.get('sort', 'email_stamp')
    sort_order = request.GET.get('order', 'desc')

    if sort_field.lstrip('-') not in ALLOWED_SORT_FIELDS:
        sort_field = 'email_stamp'

    if sort_order == 'desc' and not sort_field.startswith('-'):
        sort_field = f'-{sort_field}'

    return queryset.order_by(sort_field), sort_field.lstrip('-'), sort_order


def _get_list_from_request(request, param_name):
    """
    Возвращает список значений параметра, поддерживая как множественные параметры,
    так и строку с запятыми.
    """
    values = request.GET.getlist(param_name)
    if not values and request.GET.get(param_name):
        values = [request.GET.get(param_name)]
    # Делим каждый элемент по запятой: одиночная строка 'a,b' и смешанные
    # 'tag=1,a&tag=b' дают плоский список; пустые отбрасываем.
    flat = []
    for v in values:
        flat.extend([p for p in str(v).split(',') if p])
    return flat


def _safe_next(request, fallback_view, **kwargs):
    """Безопасный возврат к месту вызова (?next=) или fallback."""
    from django.utils.http import url_has_allowed_host_and_scheme
    nxt = request.POST.get('next') or request.GET.get('next')
    if nxt and url_has_allowed_host_and_scheme(
        nxt,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(nxt)
    return redirect(fallback_view, **kwargs)
