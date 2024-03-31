import pythoncom
from ProjectTDL.models import Email, EmailType

from pathlib import Path
from datetime import datetime
from django.contrib import messages

import win32com.client
import win32clipboard  # pip install pywin32

import os
from django import forms


def copy_to_clipboard(text):
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()


def text_replace(text):
    for ch in ['\\', '"', ':', '`', '*', '_', '{', '}', '[', ']', '(', ')', '>', '#', '+', '-', '.', '!', '$', '\'']:
        text = text.replace(ch, "")
    return text


class SaveAttached:
    def __init__(self, folder_path: str) -> None:
        pythoncom.CoInitialize()  # @UndefinedVariable
        self.outlook = win32com.client.Dispatch("Outlook.Application")
        self.folder_path = folder_path

    @property
    def _messages(self):
        return self.outlook.ActiveExplorer().Selection

    def _get_folder_path(self, folder_path):
        return os.path.abspath(folder_path)

    def message(self):
        return self._messages(1)

    def get_sender_email_address(self):
        return self.message().SenderEmailAddress

    def _get_message_sender(self):
        return str(self.message().Sender).replace(
            ' ', '_') if self.message().Sender else ''

    def get_message_save_name(self):
        """from topic of e-mail
            Returns:
                _type_: _description_
            """
        message_name = self.message().subject
        message_name = str(message_name)[0:30] if len(str(message_name)) > 30 else str(message_name)
        message_name = text_replace(message_name)  # replace wrong symbols
        msg_ext = f"{message_name}.msg"
        return msg_ext

    def save_message(self):
        self.message().SaveAs(
            os.path.join(
                self.folder_path, self.get_message_save_name()
            ))

    def _get_link_path(self):
        link_body = f"files wer saved to \n {self.folder_path} "
        return link_body

    # message.Body = rb'{\rtf1{Here is the }{\field{\*\fldinst { HYPERLINK "https://www.python.org" }}{\fldrslt {
    # link}}}{ I need}}'

    def saved_attached_files(self):
        for att in self.message().Attachments:
            att.SaveAsFile(os.path.join(self.folder_path, att.FileName))

    def _get_attached_files_names(self):
        file_names = []
        for att in self.message().Attachments:
            file_names.append(att.FileName)
        return file_names

    def get_old_body_text(self):
        """_summary_

            Returns:
            str: e-mail body return
        """
        return self.message().Body + "\n" * 3

    def get_new_body_text(self):
        attached = ", ".join(self._get_attached_files_names()) + "\n" * 2
        link_path = self._get_link_path() + "\n" * 2

        new_body = link_path + self.get_old_body_text()
        return new_body

    def change_mail_body(self):
        self.message().Body = self.get_new_body_text()
        return self.message().Body

    def delete_attachments(self):

        attachments = self.message().Attachments
        attachments_number = attachments.Count
        if attachments_number:
            for i in range(1, attachments_number + 1):
                attachments.Remove(i)


def get_body_text(_email: SaveAttached):
    body_text = _email.get_old_body_text()
    data = 'From'.join(body_text.split('From')[:-1])
    return data if data else body_text


def make_folder(_data_path: str):
    Path(_data_path).mkdir(parents=True, exist_ok=True)
    _is_folder_exist = os.path.isdir(_data_path)
    if _is_folder_exist:
        copy_to_clipboard(_data_path)


def parsing_form(_form: forms.ModelForm) -> forms.ModelForm:
    project_site = _form.cleaned_data['project_site'].name
    contractor = _form.cleaned_data['contractor'].name
    email_type = getattr(EmailType, _form.cleaned_data['email_type']).value
    name = _form.cleaned_data['name']
    parent = _form.cleaned_data['parent'].project_site.name if _form.cleaned_data.get('parent') else ''
    year = str(datetime.now().year)
    today = datetime.today().strftime('%Y_%m_%d')
    _data_path = os.path.join(
        'C:\\', 'Bitrix 24', 'Переписка', project_site, contractor, email_type, year, f'{today}_{name}'
    )
    _form.cleaned_data['link'] = _data_path
    return _form


def parsing_email_data_to_form(_form: forms.ModelForm, request) -> forms.ModelForm:
    try:
        email = SaveAttached(_form.cleaned_data['link'])
        email.saved_attached_files()
        _form.cleaned_data['subject'] = email.message().Subject
        _form.cleaned_data['body'] = get_body_text(email)
        _form.cleaned_data['sender'] = email.message().Sender
        messages.success(request, f'E mail {email.message().Subject} parsing ok')
        return _form
    except Exception as e:
        _form.add_error(None, str(e))
        messages.error(request, 'парсинг e-mail не удался' + str(e))
        return _form


def add_form_data_to_data_base(_form: forms.ModelForm, request):
    try:
        Email.objects.create(**_form.cleaned_data)
        messages.success(request, 'Добавление данных прошло успешно')
    # return redirect('home')
    except Exception as e:
        _form.add_error(None, str(e))
        messages.error(request, 'Не смог добавить в базу данных', str(e))
