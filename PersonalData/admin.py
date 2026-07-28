from django import forms
from django.contrib import admin

from AdminUtils import get_filtered_registered_models, get_standard_display_list
from PersonalData.models import PersonalPassword, PersonalNote


@admin.register(PersonalPassword)
class PersonalPasswordAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'login', 'category', 'password_masked', 'favorite', 'update_stamp')
    list_display_links = ('id', 'name')
    list_filter = ('category', 'favorite')
    search_fields = ('name', 'login', 'url')
    list_editable = ('favorite',)
    list_per_page = 30

    class _Form(forms.ModelForm):
        password = forms.CharField(
            label='Пароль', required=False,
            widget=forms.PasswordInput(render_value=False),
            help_text='Оставьте пустым, чтобы не менять сохранённый пароль',
        )

        class Meta:
            model = PersonalPassword
            fields = ['name', 'url', 'login', 'category', 'notes', 'favorite']

        def clean_password(self):
            return self.cleaned_data.get('password') or None

    form = _Form

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change=change, **kwargs)
        return form

    def save_model(self, request, obj, form, change):
        new_pass = form.cleaned_data.get('password')
        if new_pass:
            obj.set_password(new_pass)
        super().save_model(request, obj, form, change)

    @admin.display(description='Пароль')
    def password_masked(self, obj):
        return '••••••••••'


@admin.register(PersonalNote)
class PersonalNoteAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'tags', 'pinned', 'update_stamp')
    list_display_links = ('id', 'name')
    list_editable = ('pinned',)
    search_fields = ('name', 'body', 'tags')
    list_per_page = 30


@admin.register(*[m for m in get_filtered_registered_models('PersonalData')
                  if m not in (PersonalPassword, PersonalNote)])
class UniversalAdmin(admin.ModelAdmin):
    list_display_links = ('id', 'name')
    list_per_page = 20

    def get_list_display(self, request):
        return get_standard_display_list(
            self.model, excluding_list=['creation_stamp', 'update_stamp', 'link', 'body']
        )