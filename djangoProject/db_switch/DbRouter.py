from .thread_local import get_current_db

SWITCHABLE_APPS = {
    'ProjectTDL', 'StaticData', 'ProjectContract',
    'Emails', 'email_ui', 'TelegramParser',
}

PERSONAL_APPS = {'PersonalData'}


class DatabaseSwitchRouter:
    def _route_to(self, model):
        app = model._meta.app_label
        if app in PERSONAL_APPS:
            return 'personal_db'
        if app in SWITCHABLE_APPS:
            return get_current_db()
        return 'default'

    def db_for_read(self, model, **hints):
        return self._route_to(model)

    def db_for_write(self, model, **hints):
        return self._route_to(model)

    def allow_relation(self, obj1, obj2, **hints):
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label in PERSONAL_APPS:
            return db == 'personal_db'
        if app_label in SWITCHABLE_APPS:
            return db == get_current_db()
        return db == 'default'
