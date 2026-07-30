from .thread_local import get_current_db


class DatabaseSwitchRouter:
    def _route_to(self, model):
        return get_current_db()

    def db_for_read(self, model, **hints):
        return self._route_to(model)

    def db_for_write(self, model, **hints):
        return self._route_to(model)

    def allow_relation(self, obj1, obj2, **hints):
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return db == get_current_db()
