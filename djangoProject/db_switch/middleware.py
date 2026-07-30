from .thread_local import set_current_db

class DatabaseSwitchMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        db_mode = request.session.get('db_mode', 'work')
        if db_mode == 'personal':
            set_current_db('personal_db')
        else:
            set_current_db('default')
        return self.get_response(request)
