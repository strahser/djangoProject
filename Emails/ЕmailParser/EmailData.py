from dataclasses import dataclass
import datetime


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
