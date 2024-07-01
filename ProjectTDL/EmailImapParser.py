# pip install imap-tools

import os
import datetime
from collections import namedtuple

from imap_tools import MailBox, MailMessage, AND, A
from dataclasses import dataclass

from ProjectTDL.models import Email

YA_HOST = "imap.yandex.ru"
YA_PORT = 993
YA_USER = "strakhov.s@cimrus.com"
YA_PASSWORD = "mircxhzbiwryssjp"
UID_LIST = list(Email.objects.values_list('uid', flat=True).all())


@dataclass
class EmailData:
    uid: str
    email_type: str
    name: str
    parent: str
    link: str
    subject: str
    body: str
    sender: str
    data: datetime.datetime


def clean(text):
    # clean text for creating a folder
    return "".join(c if c.isalnum() else "_" for c in text)


class BaseAttachedClass:
    def __init__(self, attached, root_folder_path_name):
        self.attached = attached
        self.root_folder_path_name = root_folder_path_name


class EmailImapAttachedEmailType(BaseAttachedClass):
    def __init__(self, attached, root_folder_path_name):
        super().__init__(attached, root_folder_path_name)
        self.attached = MailMessage.from_bytes(attached.payload)
        self.clean_subject = clean(attached.subject[0:40])

    def get_attached_path(self):
        return os.path.join(self.root_folder_path_name, self.clean_subject)

    def save_attached(self):
        with open(self.get_attached_path(), "w", encoding="utf-8") as f:
            f.write(self.attached.html)


class EmailImapAttachedGenericType(BaseAttachedClass):
    def __init__(self, attached, root_folder_path_name):
        super().__init__(attached, root_folder_path_name)

    def get_attached_path(self):
        return os.path.join(self.root_folder_path_name, self.attached)

    def save_attached(self):
        with open(f"{self.root_folder_path_name}/{self.attached.filename}", 'wb') as f:
            f.write(self.attached.payload)


class EmailImapMessage:
    def __init__(self, root_path, msg: MailBox.fetch):
        self.msg = msg
        self.clean_subject = clean(msg.subject[0:40])
        self.clean_message_time_stamp = clean(msg.date.strftime("%Y_%m_%d_%H_%M_%S"))
        self.html_message_name = 'index.html'
        self.folder_path_name = os.path.join(root_path, f"{msg.uid}_{self.clean_subject}")
        self.message_path_name = None

    def save_e_mail_to_html(self, ):
        self.message_path_name = f'{self.folder_path_name}/{self.html_message_name}'
        with open(self.message_path_name, "w", encoding="utf-8") as f:
            f.write(self.msg.html)


class DbEmailImapMessageSerializer:
    def __init__(self, email_type, link, msg: MailBox.fetch):
        self.uid = msg.uid
        self.email_type = email_type
        self.subject = msg.subject
        self.link = link
        self.body = msg.html
        self.sender = msg.from_values.name
        self.receiver = msg.to_values
        self.email_stamp = msg.date
        self.creation_stamp = datetime.datetime.now()

    def create_record(self):
        receiver_name = None
        if len(self.receiver) == 1:
            receiver_name = self.receiver[0].name
        if len(self.receiver) > 1:
            receiver_name = [val.name for val in self.receiver]

        Email.objects.get_or_create(
            uid=self.uid, email_type=self.email_type,
            subject=self.subject,
            link=self.link, body=self.body, sender=self.sender,
            receiver=receiver_name, email_stamp=self.email_stamp,
        )


class ParsingImapEmailToDB:
    def __init__(self, root_folder_path):
        self.root_folder_path = root_folder_path

    @staticmethod
    def is_email_attached(attached_file):
        if '.eml' in attached_file.filename:
            return True
        else:
            return False

    @staticmethod
    def _create_folder(_directory):
        os.makedirs(_directory, exist_ok=True)

    def choose_and_save_attachments(self, attach, message):
        if self.is_email_attached(attach):
            attachment = EmailImapAttachedEmailType(attach, message.folder_path_name)
            attachment.save_attached()
        else:
            attachment = EmailImapAttachedGenericType(attach, message.folder_path_name)
            attachment.save_attached()

    def main(self, email_type, folder, limit=None):
        create_action_list = []
        skip_action_list = []
        with MailBox(YA_HOST).login(YA_USER, YA_PASSWORD, initial_folder=folder) as mailbox:
            for en, msg in enumerate(mailbox.fetch(reverse=True, limit=limit)):
                uid_condition = msg.uid not in UID_LIST
                if uid_condition==True:
                    create_action_list.append(msg.uid)
                    try:
                        message = EmailImapMessage(self.root_folder_path, msg)
                        self._create_folder(message.folder_path_name)
                        message.save_e_mail_to_html()
                        for attach in msg.attachments:
                            self.choose_and_save_attachments(attach, message)
                        serializer = DbEmailImapMessageSerializer(email_type, message.folder_path_name, msg)
                        serializer.create_record()
                    except Exception as e:
                        print(e)
                else:
                    skip_action_list.append(msg.uid)
        print("create_action_list")
        print(len(create_action_list))
        print("skip_action_list")
        print(len(skip_action_list))
