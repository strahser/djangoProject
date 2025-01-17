
import datetime
from imap_tools import MailBox, MailMessage, AND, A

from ProjectTDL.models import Email
from ProjectTDL.ЕmailParser.EmailImapMessage import EmailBody


class DbEmailImapMessageSerializer:
	def __init__(self, email_type, link, msg: MailBox.fetch):
		self.uid = msg.uid
		self.email_type = email_type
		self.subject = msg.subject
		self.link = link
		self.body = EmailBody(msg).created_body
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
			link=self.link,
			body=self.body,
			sender=self.sender,
			receiver=receiver_name,
			email_stamp=self.email_stamp,
		)