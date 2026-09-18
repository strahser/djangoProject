"""Админка реестров: один объект — свой раздел (таблицы doc_m1_*, doc_k1_*).

Справочники (проекты, типы зданий, разделы, подрядчики, подписанты) — общие.
Смешивание невозможно: у каждой таблицы свой ModelAdmin со своим queryset.
"""
from django.contrib import admin
from django.http import HttpResponse

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


class _RevisionInlineBase(admin.TabularInline):
    extra = 0
    fields = ('rev_no', 'status', 'source', 'size', 'email', 'task')
    show_change_link = True


class _IssueInlineBase(admin.TabularInline):
    extra = 0
    fields = ('waybill_no', 'waybill_date', 'network_path', 'archived_old_rev')


class _HistoryRemarkInlineBase(admin.TabularInline):
    extra = 0
    fields = ('text', 'author', 'remark_date')
    verbose_name = 'Замечание (история)'
    verbose_name_plural = 'Замечания (история accdb)'


class M1RevisionInline(_RevisionInlineBase):
    model = M1Revision


class K1RevisionInline(_RevisionInlineBase):
    model = K1Revision


class M1IssueInline(_IssueInlineBase):
    model = M1Issue


class K1IssueInline(_IssueInlineBase):
    model = K1Issue


class M1HistoryRemarkInline(_HistoryRemarkInlineBase):
    model = M1Remark
    fk_name = 'entry'


class K1HistoryRemarkInline(_HistoryRemarkInlineBase):
    model = K1Remark
    fk_name = 'entry'


class BuildingNoFilter(admin.SimpleListFilter):
    """Фильтр «Номер здания»: в списке — № (1.4, 2.1…), а не наименования.

    Стандартный RelatedOnly показывает str() здания (= наименование) и визуально
    дублирует фильтр «Наименование здания». Параметр оставляем штатный
    building_no__id__exact, чтобы работали обычные URL.
    """

    title = 'номер здания'
    parameter_name = 'building_no__id__exact'

    def lookups(self, request, model_admin):
        entry_model = model_admin.model
        bmodel = entry_model._meta.get_field('building_no').remote_field.model
        used = (entry_model.objects.exclude(building_no__isnull=True)
                .values_list('building_no_id', flat=True).distinct())
        return [(b.pk, b.number or b.name)
                for b in bmodel.objects.filter(pk__in=used).order_by('code')]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(building_no_id=self.value())
        return queryset


class _EntryAdminBase(admin.ModelAdmin):
    """Порядок колонок — как в исходнике accdb: код, здание, раздел, № здания, файл, разраб., согласование."""

    list_display = ('code', 'get_building', 'get_section', 'get_building_no',
                    'file_name', 'get_developer', 'approval_status', 'submit_date', 'contract')
    list_filter = ('approval_status', 'section',
                   ('building', admin.RelatedOnlyFieldListFilter),
                   BuildingNoFilter,
                   'developer')
    search_fields = ('cipher', 'file_name', 'change_descr',
                     'building__name', 'section__short', 'developer__name')
    list_select_related = ('contract', 'section', 'building', 'building_no', 'developer')
    actions = ('make_approval_sheet',)

    @admin.action(description='Сформировать лист согласования (PDF) для выбранных')
    def make_approval_sheet(self, request, queryset):
        from .pdf_forms import approval_sheet_multi
        from .services import signers_for

        entries = list(queryset.select_related(
            'building', 'building_no', 'section', 'developer').order_by('code')[:100])
        if not entries:
            self.message_user(request, 'Ничего не выбрано', level='error')
            return None
        pdf = approval_sheet_multi(entries, signers_for())
        codes = '_'.join(str(e.code) for e in entries[:8])
        resp = HttpResponse(pdf, content_type='application/pdf')
        resp['Content-Disposition'] = (
            f'attachment; filename="list-soglasovaniya-{codes}.pdf"')
        return resp

    @admin.display(description='Наименование здания', ordering='building__name')
    def get_building(self, obj):
        return obj.building.name if obj.building else '—'

    @admin.display(description='Раздел', ordering='section__short')
    def get_section(self, obj):
        return obj.section.short if obj.section else '—'

    @admin.display(description='Номер здания', ordering='building_no__number')
    def get_building_no(self, obj):
        return obj.building_no.number if obj.building_no else '—'

    @admin.display(description='Разраб.', ordering='developer__name')
    def get_developer(self, obj):
        return obj.developer.name if obj.developer else '—'


@admin.register(M1Entry)
class M1EntryAdmin(_EntryAdminBase):
    inlines = (M1RevisionInline, M1IssueInline, M1HistoryRemarkInline)


@admin.register(K1Entry)
class K1EntryAdmin(_EntryAdminBase):
    inlines = (K1RevisionInline, K1IssueInline, K1HistoryRemarkInline)


class _BuildingAdminBase(admin.ModelAdmin):
    list_display = ('code', 'building_type', 'number', 'name')
    list_filter = ('building_type',)
    search_fields = ('number', 'name')
    list_select_related = ('building_type',)


@admin.register(M1Building)
class M1BuildingAdmin(_BuildingAdminBase):
    pass


@admin.register(K1Building)
class K1BuildingAdmin(_BuildingAdminBase):
    pass


class _RevisionAdminBase(admin.ModelAdmin):
    list_display = ('entry', 'rev_no', 'status', 'source', 'size', 'received_at', 'task')
    list_filter = ('status', 'source')
    search_fields = ('entry__cipher', 'entry__file_name', 'submitted_folder')
    list_select_related = ('entry', 'task', 'email')


@admin.register(M1Revision)
class M1RevisionAdmin(_RevisionAdminBase):
    pass


@admin.register(K1Revision)
class K1RevisionAdmin(_RevisionAdminBase):
    pass


class _CheckAdminBase(admin.ModelAdmin):
    list_display = ('revision', 'verdict', 'checked_by', 'checked_at')
    list_filter = ('verdict',)


@admin.register(M1Check)
class M1CheckAdmin(_CheckAdminBase):
    pass


@admin.register(K1Check)
class K1CheckAdmin(_CheckAdminBase):
    pass


class _RemarkAdminBase(admin.ModelAdmin):
    list_display = ('revision', 'entry', 'author', 'remark_date', 'sent_at', 'reply_at')
    list_select_related = ('revision', 'entry')


@admin.register(M1Remark)
class M1RemarkAdmin(_RemarkAdminBase):
    pass


@admin.register(K1Remark)
class K1RemarkAdmin(_RemarkAdminBase):
    pass


class _IssueAdminBase(admin.ModelAdmin):
    list_display = ('entry', 'waybill_no', 'waybill_date', 'network_path', 'archived_old_rev', 'issued_at')
    list_select_related = ('entry',)


@admin.register(M1Issue)
class M1IssueAdmin(_IssueAdminBase):
    pass


@admin.register(K1Issue)
class K1IssueAdmin(_IssueAdminBase):
    pass


class _ChangeLogAdminBase(admin.ModelAdmin):
    list_display = ('entry', 'revision', 'field', 'source', 'changed_by', 'changed_at')
    list_filter = ('source',)
    list_select_related = ('entry', 'revision')
    readonly_fields = ('changed_at',)


@admin.register(M1ChangeLog)
class M1ChangeLogAdmin(_ChangeLogAdminBase):
    pass


@admin.register(K1ChangeLog)
class K1ChangeLogAdmin(_ChangeLogAdminBase):
    pass


@admin.register(DocProject)
class DocProjectAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'customer', 'designer')
    fields = ('code', 'name', 'customer', 'object_name', 'object_address', 'designer')


@admin.register(DocSection)
class DocSectionAdmin(admin.ModelAdmin):
    list_display = ('code', 'short', 'name')
    search_fields = ('short', 'name')


@admin.register(DocDeveloper)
class DocDeveloperAdmin(admin.ModelAdmin):
    list_display = ('code', 'name')
    search_fields = ('name',)


@admin.register(DocSigner)
class DocSignerAdmin(admin.ModelAdmin):
    list_display = ('order', 'position', 'company', 'person', 'mark', 'stamp')
    list_editable = ('stamp',)
