from .thread_local import set_current_db


def _sync_menu_names(db_mode):
    """Раздел «Проекты» в меню админки называется по текущей БД."""
    from django.apps import apps
    app_config = apps.get_app_config('ProjectTDL')
    if db_mode == 'personal':
        app_config.verbose_name = 'Личные'
    else:
        app_config.verbose_name = 'Рабочие/Симрус'


class DatabaseSwitchMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        db_mode = request.session.get('db_mode', 'work')
        if db_mode == 'personal':
            set_current_db('personal_db')
        else:
            set_current_db('default')
        _sync_menu_names(db_mode)
        return self.get_response(request)
