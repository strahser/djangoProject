from django.contrib import admin
from django.http import HttpResponse

from .models import (
    DocBuilding,
    DocChangeLog,
    DocCheck,
    DocDeveloper,
    DocIssue,
    DocProject,
    DocRegisterEntry,
    DocRemark,
    DocRevision,
    DocSection,
    DocSigner,
)


class DocRevisionInline(admin.TabularInline):
    model = DocRevision
    extra = 0
    fields = ('rev_no', 'status', 'source', 'size', 'email', 'task')
    show_change_link = True


class DocIssueInline(admin.TabularInline):
    model = DocIssue
    extra = 0
    fields = ('waybill_no', 'waybill_date', 'network_path', 'archived_old_rev')


class DocSignerInline(admin.TabularInline):
    model = DocSigner
    extra = 0
    fields = ('order', 'position', 'company', 'person', 'mark')


class DocHistoryRemarkInline(admin.TabularInline):
    model = DocRemark
    extra = 0
    fields = ('text', 'author', 'remark_date')
    verbose_name = 'Замечание (история)'
    verbose_name_plural = 'Замечания (история accdb)'


@admin.register(DocRegisterEntry)
class DocRegisterEntryAdmin(admin.ModelAdmin):
    """Порядок колонок — как в исходнике accdb: код, здание, раздел, № здания, файл, разраб., согласование."""

    list_display = ('code', 'get_building', 'get_section', 'get_building_no',
                    'file_name', 'get_developer', 'approval_status', 'submit_date', 'contract')
    list_filter = ('approval_status', 'section', 'developer', 'project')
    search_fields = ('cipher', 'file_name', 'change_descr',
                     'building__name', 'section__short', 'developer__name')
    list_select_related = ('contract', 'section', 'building', 'building_no', 'developer')
    inlines = (DocRevisionInline, DocIssueInline, DocHistoryRemarkInline)
    actions = ('make_approval_sheet',)

    @admin.action(description='Сформировать лист согласования (PDF) для выбранных')
    def make_approval_sheet(self, request, queryset):
        from .pdf_forms import approval_sheet_multi
        from .services import signers_for

        entries = list(queryset.select_related(
            'building', 'building_no', 'section', 'developer', 'project').order_by('code')[:100])
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


@admin.register(DocProject)
class DocProjectAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'customer', 'designer')
    fields = ('code', 'name', 'customer', 'object_name', 'object_address', 'designer')


@admin.register(DocBuilding)
class DocBuildingAdmin(admin.ModelAdmin):
    list_display = ('code', 'project', 'number', 'name')
    list_filter = ('project',)
    search_fields = ('number', 'name')
    inlines = (DocSignerInline,)


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
    list_display = ('building', 'order', 'position', 'company', 'person', 'mark', 'stamp')
    list_filter = ('building',)
    list_editable = ('stamp',)


@admin.register(DocRevision)
class DocRevisionAdmin(admin.ModelAdmin):
    list_display = ('entry', 'rev_no', 'status', 'source', 'size', 'received_at', 'task')
    list_filter = ('status', 'source')
    search_fields = ('entry__cipher', 'entry__file_name', 'submitted_folder')
    list_select_related = ('entry', 'task', 'email')


@admin.register(DocCheck)
class DocCheckAdmin(admin.ModelAdmin):
    list_display = ('revision', 'verdict', 'checked_by', 'checked_at')
    list_filter = ('verdict',)


@admin.register(DocRemark)
class DocRemarkAdmin(admin.ModelAdmin):
    list_display = ('revision', 'entry', 'author', 'remark_date', 'sent_at', 'reply_at')
    list_select_related = ('revision', 'entry')


@admin.register(DocIssue)
class DocIssueAdmin(admin.ModelAdmin):
    list_display = ('entry', 'waybill_no', 'waybill_date', 'network_path', 'archived_old_rev', 'issued_at')
    list_select_related = ('entry',)


@admin.register(DocChangeLog)
class DocChangeLogAdmin(admin.ModelAdmin):
    list_display = ('entry', 'revision', 'field', 'source', 'changed_by', 'changed_at')
    list_filter = ('source',)
    readonly_fields = ('changed_at',)
