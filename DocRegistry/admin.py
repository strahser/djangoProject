from django.contrib import admin

from .models import (
    DocChangeLog,
    DocCheck,
    DocIssue,
    DocRegisterEntry,
    DocRemark,
    DocRevision,
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


@admin.register(DocRegisterEntry)
class DocRegisterEntryAdmin(admin.ModelAdmin):
    list_display = ('code', 'cipher', 'building_name', 'approval_status', 'submit_date', 'contract')
    list_filter = ('approval_status', 'submitted_flag')
    search_fields = ('cipher', 'file_name', 'building_name', 'change_descr')
    list_select_related = ('contract',)
    inlines = (DocRevisionInline, DocIssueInline)


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
    list_display = ('revision', 'sent_at', 'reply_at')
    list_select_related = ('revision',)


@admin.register(DocIssue)
class DocIssueAdmin(admin.ModelAdmin):
    list_display = ('entry', 'waybill_no', 'waybill_date', 'network_path', 'archived_old_rev', 'issued_at')
    list_select_related = ('entry',)


@admin.register(DocChangeLog)
class DocChangeLogAdmin(admin.ModelAdmin):
    list_display = ('entry', 'revision', 'field', 'source', 'changed_by', 'changed_at')
    list_filter = ('source',)
    readonly_fields = ('changed_at',)
