import os

from imap_tools import MailBox, MailMessage, AND, A

from ProjectTDL.ЕmailParser.EmailImapMessage import EmailImapMessage
from ProjectTDL.ЕmailParser.DbEmailImapMessageSerializer import DbEmailImapMessageSerializer
from ProjectTDL.ЕmailParser.EmailConfig import YA_HOST, YA_USER, YA_PASSWORD
from ProjectTDL.ЕmailParser.EmailImapAttachedEmailType import EmailImapAttachedEmailType
from ProjectTDL.ЕmailParser.EmailImapAttachedGenericType import EmailImapAttachedGenericType
from ProjectTDL.models import Email

UID_LIST = list(Email.objects.values_list('uid', flat=True).all())


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
				if uid_condition == True:
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