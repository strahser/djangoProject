from django.contrib import admin

from .models import (
    EmailTag, EmailEmailTag, Contact, ContactEmail,
    SMTPAccount, EmailTemplate, EmailTemplateVariable,
    EmailRule, EmailAutomationLog, SavedFilter, EmailTaskLink,
)


class ContactEmailInline(admin.TabularInline):
    model = ContactEmail
    extra = 1


class EmailEmailTagInline(admin.TabularInline):
    model = EmailEmailTag
    extra = 1


class EmailTemplateVariableInline(admin.TabularInline):
    model = EmailTemplateVariable
    extra = 1


@admin.register(EmailTag)
class EmailTagAdmin(admin.ModelAdmin):
    list_display = ['name', 'color', 'is_system', 'created_at']
    list_editable = ['color', 'is_system']
    search_fields = ['name']


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ['name', 'company', 'phone', 'primary_email', 'is_active']
    list_filter = ['is_active', 'company']
    search_fields = ['name', 'emails__email']
    inlines = [ContactEmailInline]


@admin.register(ContactEmail)
class ContactEmailAdmin(admin.ModelAdmin):
    list_display = ['email', 'contact', 'label', 'is_primary']
    list_filter = ['label', 'is_primary']
    search_fields = ['email', 'contact__name']


@admin.register(SMTPAccount)
class SMTPAccountAdmin(admin.ModelAdmin):
    list_display = ['name', 'host', 'port', 'username', 'from_email', 'is_default', 'is_active']
    list_editable = ['is_default', 'is_active']


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'subject_template', 'is_html', 'created_by', 'created_at']
    search_fields = ['name', 'subject_template']
    inlines = [EmailTemplateVariableInline]


@admin.register(EmailRule)
class EmailRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'priority', 'created_by', 'created_at']
    list_editable = ['is_active', 'priority']
    list_filter = ['is_active']


@admin.register(EmailAutomationLog)
class EmailAutomationLogAdmin(admin.ModelAdmin):
    list_display = ['rule', 'email', 'executed_at', 'success', 'action_taken']
    list_filter = ['success', 'rule']
    readonly_fields = ['executed_at']


@admin.register(SavedFilter)
class SavedFilterAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'folder', 'is_default', 'is_shared']
    list_filter = ['folder', 'user', 'is_default']


@admin.register(EmailTaskLink)
class EmailTaskLinkAdmin(admin.ModelAdmin):
    list_display = ['email', 'task', 'link_type', 'created_at']
    list_filter = ['link_type']
    search_fields = ['email__subject', 'task__name']
