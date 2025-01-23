import os

from imap_tools import MailBox

from Emails.ЕmailParser.EmailFunctions import clean


class EmailBody:
	def __init__(self, msg: MailBox.fetch, additional_text: str = None):
		self.msg = msg
		from_ = f"Отправитель:{self.msg.from_}<br>"
		to = f" Получатель:{','.join(self.msg.to)}<br>"
		date_str = f" Дата:{self.msg.date_str}<br>"
		subject = f" Тема Письма:{self.msg.subject}<br>"
		self.created_body = f"{from_}{to}{date_str}{subject}<br>{additional_text}<br>{self.msg.html}"


class EmailImapMessage:
	def __init__(self, root_path, msg: MailBox.fetch):
		self.msg = msg
		self.clean_subject = clean(msg.subject[0:40])
		self.clean_message_time_stamp = clean(msg.date.strftime("%Y_%m_%d_%H_%M_%S"))
		self.html_message_name = 'custom_table_view.html'
		self.folder_path_name = os.path.join(root_path, f"{msg.uid}_{self.clean_subject}")
		self.message_path_name = None

	def save_e_mail_to_html(self, ):
		self.message_path_name = f'{self.folder_path_name}/{self.html_message_name}'
		with open(self.message_path_name, "w", encoding="utf-8") as f:
			att_list = []
			for att in self.msg.attachments:
				att_list.append(att.filename)
			body = EmailBody(self.msg, f" Вложения:{','.join(att_list)}")
			f.write(body.created_body)

