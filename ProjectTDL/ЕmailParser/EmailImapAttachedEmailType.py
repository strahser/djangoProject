import os

from imap_tools import MailMessage

from ProjectTDL.ЕmailParser.BaseAttachedClass import BaseAttachedClass
from ProjectTDL.ЕmailParser.EmailFunctions import clean


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