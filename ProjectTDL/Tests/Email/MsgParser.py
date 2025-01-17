import datetime
import os.path
from dataclasses import dataclass

import extract_msg

# Replace 'MS_Outlook_file.msg'
# with the path to your.msg file
# pip install extract_msg
# pip install imapclient

from os import listdir
from os.path import isfile, join

import pandas as pd
import sqlite3


@dataclass
class EmailData:
    uid: str
    email_type: str
    name: str
    link: str
    body: str
    sender: str
    email_data: datetime.datetime

def clean(text):
    # clean text for creating a folder
    return "".join(c if c.isalnum() else "_" for c in text)

def add_emails_msg_to_sqlite(_mypath: str, _file_list: list[str], sqlite_connection: sqlite3.Connection):
    def create_emil_df(mail_list: [EmailData]):
        df = pd.DataFrame(mail_list)
        with open(_mypath + 'df.html', "w", encoding="utf-8") as f:
            f.write(df.to_html(escape=False))

    cursor = sqlite_connection.cursor()
    for en, msg_file in enumerate(_file_list):
        try:
            msg = extract_msg.Message(msg_file)
            uid = msg.messageId
            email_type = "IN"
            subject = msg.subject
            link = msg_file
            body = f"{link}"
            sender = msg.sender.split('@')[0]
            email_stamp = msg.date
            creation_stamp = datetime.datetime.now()
            values = (uid, email_type, subject, link, body, sender, email_stamp, creation_stamp)

            sqlite_insert_query = f"""INSERT INTO ProjectTDL_email
                                  (uid, email_type, name, link, body,sender,email_stamp,creation_stamp)
                                  VALUES
                                  (?,?,?,?,?,?,?,?);"""

            count = cursor.execute(sqlite_insert_query, values)
            sqlite_connection.commit()
            if msg.body:
                with open(link+str(en), "w", encoding="utf-8") as f:
                    f.write(msg.body)
            msg.close()
        except Exception as e:
            print(e)
    cursor.close()
    sqlite_connection.close()


mypath = r'e:\Проекты Симрус\Переписка\2024-06-26_архив'
file_list = [os.path.join(mypath, f) for f in listdir(mypath) if isfile(join(mypath, f))]
sqlite_connection = sqlite3.connect(r'c:\Users\Strakhov\YandexDisk\ProjectCoding\djangoProject\db.sqlite3')
if __name__ == '__main__':
    add_emails_msg_to_sqlite(mypath, file_list, sqlite_connection)
