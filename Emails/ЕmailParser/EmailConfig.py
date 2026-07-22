import os
from django.conf import settings

YA_HOST = settings.YA_HOST
YA_PORT = settings.YA_PORT
YA_USER = settings.YA_USER
YA_PASSWORD = settings.YA_PASSWORD
E_MAIL_DIRECTORY = settings.E_MAIL_DIRECTORY

if not YA_USER or not YA_PASSWORD:
    import warnings
    warnings.warn("IMAP credentials (YA_USER, YA_PASSWORD) not configured in .env")
