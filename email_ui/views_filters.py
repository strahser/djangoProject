# -*- coding: utf-8 -*-
"""P2: вьюхи сохранённых фильтров email_ui (вынесено из views.py 1:1).

Поведение, шаблоны и url-имена не менялись.
"""
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .forms import SavedFilterForm
from .models import SavedFilter
from .services.modal_forms import save_modal_form


@login_required
def saved_filters_list(request):
    """Список сохранённых фильтров (частичный, для менеджера)."""
    filters = SavedFilter.objects.filter(Q(user=request.user) | Q(is_shared=True))
    return render(request, 'email_ui/partials/saved_filters_list.html', {'filters': filters})


@login_required
def saved_filters_modal(request):
    """Менеджер сохранённых фильтров (контент модалки)."""
    filters = SavedFilter.objects.filter(Q(user=request.user) | Q(is_shared=True))
    return render(request, 'email_ui/partials/saved_filters_modal.html', {'filters': filters})


@login_required
def save_filter_modal(request):
    """Форма сохранения текущего фильтра. Параметры — из filter_params
    (текущая форма фильтров), прокинутых при открытии."""
    initial = {'folder': request.GET.get('folder', 'inbox')}
    return render(request, 'email_ui/partials/saved_filter_form.html', {
        'form': SavedFilterForm(initial=initial),
        'filter_params': request.GET.get('filter_params', ''),
    })


@login_required
@require_http_methods(['POST'])
def toggle_pin_filter(request, pk):
    """Закрепить/открепить фильтр в сайдбаре (только свой)."""
    sf = get_object_or_404(SavedFilter, pk=pk, user=request.user)
    sf.is_pinned = not sf.is_pinned
    sf.save(update_fields=['is_pinned'])
    filters = SavedFilter.objects.filter(Q(user=request.user) | Q(is_shared=True))
    return render(request, 'email_ui/partials/saved_filters_modal.html', {'filters': filters})


@login_required
@require_http_methods(['POST'])
def save_current_filter(request):
    """Сохранить текущий фильтр."""
    form = SavedFilterForm(request.POST)

    def _save_filter():
        sf = form.save(commit=False)
        sf.user = request.user
        # Параметры — из скрытого filter_params формы сохранения (текущая
        # форма фильтров); fallback — GET (старое поведение).
        raw_params = (request.POST.get('filter_params') or '').strip()
        if raw_params:
            from django.http import QueryDict
            sf.filters = dict(QueryDict(raw_params).lists())
        else:
            sf.filters = dict(request.GET.lists())
        sf.save()
        return sf

    return save_modal_form(
        request, form, template='email_ui/partials/saved_filter_form.html',
        mode='save',
        message=lambda sf: f'Фильтр "{sf.name}" сохранён',
        save=_save_filter)


@login_required
@require_http_methods(['GET', 'POST'])
def apply_saved_filter(request, pk):
    """Применить сохранённый фильтр (редирект на inbox с параметрами)."""
    q = Q(user=request.user) | Q(is_shared=True)
    sf = get_object_or_404(SavedFilter, q, pk=pk)
    # Build URL with filter params
    from urllib.parse import urlencode
    params = {}
    for key, values in sf.filters.items():
        if len(values) == 1:
            params[key] = values[0]
        else:
            params[key] = values
    url = f"{reverse('email_ui:inbox_default')}?{urlencode(params, doseq=True)}"
    return redirect(url)


@login_required
@require_http_methods(['POST'])
def delete_saved_filter(request, pk):
    """Удалить сохранённый фильтр."""
    sf = get_object_or_404(SavedFilter, pk=pk, user=request.user)
    sf.delete()
    return HttpResponse(status=204)
