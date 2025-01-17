import os.path
import pathlib

from imap_tools import MailBox
from ProjectTDL.ЕmailParser.EmailConfig import YA_HOST, YA_USER, YA_PASSWORD
from ProjectTDL.ЕmailParser.EmailImapMessage import EmailImapMessage


def save_e_mail():
    root_folder_path = os.path.abspath("Test_data")
    initial_folder = 'INBOX'
    with MailBox(YA_HOST).login(YA_USER, YA_PASSWORD, initial_folder=initial_folder) as mailbox:
        for en, msg in enumerate(mailbox.fetch(reverse=True, limit=5)):
            message = EmailImapMessage(root_folder_path, msg)
            pathlib.Path(message.folder_path_name).mkdir(parents=True, exist_ok=True)
            message.save_e_mail_to_html()

save_e_mail()