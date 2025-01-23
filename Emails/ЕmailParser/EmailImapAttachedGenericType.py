import os
from Emails.ЕmailParser.BaseAttachedClass import BaseAttachedClass


class EmailImapAttachedGenericType(BaseAttachedClass):
	def __init__(self, attached, root_folder_path_name):
		super().__init__(attached, root_folder_path_name)

	def get_attached_path(self):
		return os.path.join(self.root_folder_path_name, self.attached)

	def save_attached(self):
		with open(f"{self.root_folder_path_name}/{self.attached.filename}", 'wb') as f:
			f.write(self.attached.payload)