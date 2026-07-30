from django.shortcuts import redirect
from django.urls import reverse


def switch_db(request):
    current = request.session.get('db_mode', 'work')
    request.session['db_mode'] = 'personal' if current == 'work' else 'work'
    next_url = request.GET.get('next') or request.META.get('HTTP_REFERER') or reverse('custom_task_view')
    return redirect(next_url)
