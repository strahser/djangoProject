from django.contrib import admin
from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme

from .models import (
    EmailTag, EmailEmailTag, Contact, ContactEmail, ContactGroup, EmailAlias,
    SMTPAccount, EmailTemplate, EmailTemplateVariable,
    EmailRule, EmailAutomationLog, EmailViewSettings, SavedFilter, EmailTaskLink,
)


class ReturnToCallerAdminMixin:
    """Возврат к месту вызова из админки.

    Ссылка вида /admin/.../add/?next=/email-ui/groups/ :
    после «Сохранить» (не «продолжить»/«добавить ещё») и после удаления —
    редирект на next. Кнопка «Вернуться» (отмена) — в change_form.html.
    """

    def _caller_url(self, request):
        nxt = request.POST.get('next') or request.GET.get('next')
        if nxt and url_has_allowed_host_and_scheme(
            nxt,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return nxt
        return None

    def response_add(self, request, obj, post_url_continue=None):
        nxt = self._caller_url(request)
        if nxt and '_save' in request.POST:
            return HttpResponseRedirect(nxt)
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        nxt = self._caller_url(request)
        if nxt and '_save' in request.POST:
            return HttpResponseRedirect(nxt)
        return super().response_change(request, obj)

    def response_delete(self, request, obj_display, obj_id):
        nxt = self._caller_url(request)
        if nxt:
            return HttpResponseRedirect(nxt)
        return super().response_delete(request, obj_display, obj_id)


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
class ContactAdmin(ReturnToCallerAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'company', 'phone', 'primary_email', 'is_active']
    list_filter = ['is_active', 'company']
    search_fields = ['name', 'emails__email']
    inlines = [ContactEmailInline]


@admin.register(ContactEmail)
class ContactEmailAdmin(ReturnToCallerAdminMixin, admin.ModelAdmin):
    list_display = ['email', 'contact', 'label', 'is_primary']
    list_filter = ['label', 'is_primary']
    search_fields = ['email', 'contact__name']


@admin.register(ContactGroup)
class ContactGroupAdmin(ReturnToCallerAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'is_active', 'updated_at']
    list_filter = ['is_active']
    search_fields = ['name', 'contacts__name', 'contacts__emails__email']
    filter_horizontal = ['contacts', 'subgroups']


@admin.register(EmailAlias)
class EmailAliasAdmin(admin.ModelAdmin):
    list_display = ['alias', 'email', 'source', 'verified', 'updated_at']
    list_filter = ['verified', 'source']
    list_editable = ['verified']
    search_fields = ['alias', 'email']


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
    list_display = ['email', 'task_node', 'link_type', 'created_at']
    list_filter = ['link_type']
    search_fields = ['email__subject', 'task_node__name']


@admin.register(EmailViewSettings)
class EmailViewSettingsAdmin(admin.ModelAdmin):
    list_display = ['user', 'show_body_preview', 'preview_length', 'updated_at']
    list_filter = ['show_body_preview']
