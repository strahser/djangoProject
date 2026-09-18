"""DMX-1: текущий пользователь запроса для сигналов аудита TaskNode."""
from .services import set_current_user


class CurrentUserMiddleware:
    """Кладёт request.user в thread-local на время запроса.

    Сигналы post_save/post_delete TaskNode забирают его через
    get_current_user(), чтобы журнал писался «с user».
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        set_current_user(user)
        try:
            return self.get_response(request)
        finally:
            set_current_user(None)
