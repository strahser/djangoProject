def db_mode(request):
    return {'db_mode': request.session.get('db_mode', 'work')}
