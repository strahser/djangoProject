
import os
import shutil
from datetime import datetime

import win32clipboard  # pip install pywin32
from django.contrib import admin
from django.contrib import messages
from import_export.admin import ImportExportModelAdmin

from Emails.models import EmailType, Email
from Emails.ЕmailParser.EmailConfig import E_MAIL_DIRECTORY
from Emails.ЕmailParser.EmailFunctions import clean


def copy_to_clipboard(text):
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()


def copytree(src, dst, symlinks=False, ignore=None):
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, symlinks, ignore)
        else:
            shutil.copy2(s, d)

@admin.register(Email)
class EmailAdmin(ImportExportModelAdmin):
    list_display = ['id', 'parent', 'email_type', 'project_site', 'building_type', 'category','info', 'contractor', 'name',
                    'subject', 'sender', 'email_stamp', 'create_admin_link']
    # list_editable = ['project_site', 'contractor']
    list_filter = ['email_type', 'project_site','info', 'contractor', 'sender']
    search_fields = ['name', 'subject', 'sender']
    list_display_links = ['id', 'name', 'subject']
    change_list_template = 'jazzmin/admin/change_list.html'
    actions = ("copy_e_mail",)

    @admin.action(description='Скопировать E-mail')
    def copy_e_mail(modeladmin, request, queryset):
        for obj in queryset:
            try:
                email_type = getattr(EmailType, obj.email_type).value
                year = str(datetime.today().year)
                today = datetime.today().strftime('%Y_%m_%d')
                folder_name = obj.name if obj.name else clean(obj.subject)
                _directory = os.path.join(E_MAIL_DIRECTORY, obj.project_site.name, obj.contractor.name, email_type,
                                          year, f'{today}_{folder_name}\\'
                                          )
                os.makedirs(_directory, exist_ok=True)
                copytree(obj.link, _directory)
                if os.path.exists(_directory):
                    copy_to_clipboard(_directory)
                    messages.success(request, f"файлы скопированы в папку {_directory}")
                else:
                    messages.error(request, f"директория не существует {_directory}")
            except Exception as e:
                messages.error(request, f"ошибки при копировании {e}")
