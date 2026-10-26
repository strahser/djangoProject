"""Единый финал modal create/edit (был _save_modal_form в views.py).

save + 204 или 400 с формой. message — строка или callable(obj)->строка;
save — колбэк вместо form.save() (commit=False + дозаполнение).
contact_create с двумя формами оставлен как есть.
"""
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render


def save_modal_form(request, form, *, template, mode, message, extra=None, save=None):
    if form.is_valid():
        obj = save() if save is not None else form.save()
        if message:
            messages.success(
                request, message(obj) if callable(message) else message)
        return HttpResponse(status=204)
    ctx = {'form': form, 'mode': mode}
    if extra:
        ctx.update(extra)
    return render(request, template, ctx, status=400)
