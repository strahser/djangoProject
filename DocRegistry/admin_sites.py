"""Отдельные админ-панели реестров: одна панель — один объект.

- /admin-m1/ — только таблицы М1 + общие справочники;
- /admin-k1/ — только таблицы К1 + общие справочники;
- /admin/ (штатная) — всё сразу, техническая.

Смешивание исключено: в панели М1 вообще нет моделей К1 (и наоборот).
Общие справочники (проекты, типы зданий, разделы, подрядчики, подписанты)
подключены в обе панели — они едины для приложения.
"""
from django.contrib.admin import AdminSite

from . import admin as reg_admin
from .models import (
    DocDeveloper,
    DocProject,
    DocSection,
    DocSigner,
    K1Building,
    K1ChangeLog,
    K1Check,
    K1Entry,
    K1Issue,
    K1Remark,
    K1Revision,
    M1Building,
    M1ChangeLog,
    M1Check,
    M1Entry,
    M1Issue,
    M1Remark,
    M1Revision,
)


class RegistryAdminSite(AdminSite):
    """Панель одного реестра: свой порядок моделей (реестр первым)."""

    #: object_name моделей по порядку показа.
    model_order: tuple = ()

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label)
        order = {name: i for i, name in enumerate(self.model_order)}
        for app in app_list:
            app['models'].sort(key=lambda m: order.get(m['object_name'], 999))
        return app_list


m1_site = RegistryAdminSite(name='m1admin')
m1_site.site_header = 'Реестр М1 — администрирование'
m1_site.site_title = 'Реестр М1'
m1_site.index_title = 'М1 · Волоколамск: реестр и справочники'
m1_site.model_order = (
    'M1Entry', 'M1Building', 'M1Revision', 'M1Check', 'M1Remark', 'M1Issue',
    'M1ChangeLog', 'DocProject', 'DocSection', 'DocDeveloper',
    'DocSigner',
)

k1_site = RegistryAdminSite(name='k1admin')
k1_site.site_header = 'Реестр К1 — администрирование'
k1_site.site_title = 'Реестр К1'
k1_site.index_title = 'К1 · Калуга: реестр и справочники'
k1_site.model_order = (
    'K1Entry', 'K1Building', 'K1Revision', 'K1Check', 'K1Remark', 'K1Issue',
    'K1ChangeLog', 'DocProject', 'DocSection', 'DocDeveloper',
    'DocSigner',
)

_M1_MODELS = (
    (M1Entry, reg_admin.M1EntryAdmin),
    (M1Building, reg_admin.M1BuildingAdmin),
    (M1Revision, reg_admin.M1RevisionAdmin),
    (M1Check, reg_admin.M1CheckAdmin),
    (M1Remark, reg_admin.M1RemarkAdmin),
    (M1Issue, reg_admin.M1IssueAdmin),
    (M1ChangeLog, reg_admin.M1ChangeLogAdmin),
)

_K1_MODELS = (
    (K1Entry, reg_admin.K1EntryAdmin),
    (K1Building, reg_admin.K1BuildingAdmin),
    (K1Revision, reg_admin.K1RevisionAdmin),
    (K1Check, reg_admin.K1CheckAdmin),
    (K1Remark, reg_admin.K1RemarkAdmin),
    (K1Issue, reg_admin.K1IssueAdmin),
    (K1ChangeLog, reg_admin.K1ChangeLogAdmin),
)

_SHARED_MODELS = (
    (DocProject, reg_admin.DocProjectAdmin),
    (DocSection, reg_admin.DocSectionAdmin),
    (DocDeveloper, reg_admin.DocDeveloperAdmin),
    (DocSigner, reg_admin.DocSignerAdmin),
)

for _model, _admin in _M1_MODELS + _SHARED_MODELS:
    m1_site.register(_model, _admin)

for _model, _admin in _K1_MODELS + _SHARED_MODELS:
    k1_site.register(_model, _admin)
