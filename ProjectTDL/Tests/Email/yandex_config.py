import os

from django.test import TestCase

# Create your tests here.

import imaplib
import email

from ProjectTDL.ЕmailParser.EmailConfig import YA_HOST, YA_PASSWORD, YA_USER

mail = imaplib.IMAP4_SSL(YA_HOST)
mail.login(YA_USER, YA_PASSWORD)
mail.list()
mail.select("inbox")

result, data = mail.search(None, "ALL")

ids = data[0][:-10]
id_list = ids.split()
for email_id in id_list:
    result, data = mail.fetch(email_id, '(RFC822)')
    raw_email = data[0][1]
    print(raw_email)
    email_message = email.message_from_bytes(raw_email)
    for part in email_message.walk():
        if part.get_content_maintype() == 'multipart':
            # Skip multipart content
            continue
        if part.get('Content-Disposition') is None:
            # Skip parts with no filename
            continue
        filename = part.get_filename()
        try:
            filepath = os.path.join(r'/ProjectTDL/temp', filename)
            # Save the attachment
            with open(filepath, 'wb') as f:
                f.write(part.get_payload(decode=True))
        except:
            None

# Disconnect from the server
mail.logout()