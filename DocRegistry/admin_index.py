"""Группировка DocRegistry на главной /admin/: «Реестр М1», «Реестр К1», «Справочники РД».

Штатный индекс админки группирует по приложению (один блок DocRegistry).
Здесь get_app_list дефолтного сайта разбивает этот блок на три псевдо-приложения —
только для отображения (app_label сохраняется, все ссылки/права работают).
Совместимо с Grappelli: его шаблон использует тот же app_list.
"""
from __future__ import annotations

_M1_MODELS = frozenset({
    'M1Entry', 'M1Building', 'M1Revision', 'M1Check', 'M1Remark', 'M1Issue',
    'M1ChangeLog',
})
_K1_MODELS = frozenset({
    'K1Entry', 'K1Building', 'K1Revision', 'K1Check', 'K1Remark', 'K1Issue',
    'K1ChangeLog',
})

_M1_ORDER = (
    'M1Entry', 'M1Building', 'M1Revision', 'M1Check', 'M1Remark', 'M1Issue',
    'M1ChangeLog',
)
_K1_ORDER = (
    'K1Entry', 'K1Building', 'K1Revision', 'K1Check', 'K1Remark', 'K1Issue',
    'K1ChangeLog',
)
_SHARED_ORDER = (
    'DocProject', 'DocSection', 'DocDeveloper', 'DocSigner',
)

_GROUPS = (
    ('Реестр М1 · Волоколамск', _M1_MODELS, _M1_ORDER),
    ('Реестр К1 · Калуга', _K1_MODELS, _K1_ORDER),
    ('Справочники РД (общие)', None, _SHARED_ORDER),
)


def _ordered(models, wanted, order):
    by_name = {m['object_name']: m for m in models}
    return [by_name[n] for n in order if n in by_name]


def patch_admin_index(site):
    """Разбить блок DocRegistry на главной странице админки на три группы."""
    orig_get_app_list = site.get_app_list

    def get_app_list(request, app_label=None):
        app_list = orig_get_app_list(request, app_label)
        if app_label is not None:
            return app_list
        out = []
        for app in app_list:
            if app.get('app_label') != 'DocRegistry':
                out.append(app)
                continue
            models = app['models']
            names = {m['object_name'] for m in models}
            for title, want, order in _GROUPS:
                if want is None:
                    chunk = [m for m in models
                             if m['object_name'] not in _M1_MODELS
                             and m['object_name'] not in _K1_MODELS]
                    chunk = _ordered(chunk, None, order) or chunk
                else:
                    if not (names & want):
                        continue
                    chunk = _ordered(models, want, order)
                if not chunk:
                    continue
                out.append({**app, 'name': title, 'models': chunk})
        return out

    # Обычное присваивание (без __get__): функция в instance __dict__ не
    # биндится, поэтому request/app_label приходят как есть.
    site.get_app_list = get_app_list
