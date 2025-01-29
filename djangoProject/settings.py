"""
Django settings for djangoProject project.

Generated by 'django-admin startproject' using Django 5.0.3.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.0/ref/settings/
charting
https://github.com/zostera/django-charting
полезные пакеты
"admin_interface",
"colorfield",
'django_mailbox',
'admin_action_tools',
'widget_tweaks',
'admin_confirm',
'slick_reporting',
'django_admin_row_actions',
'grappelli',
'grappelli.dashboard',
"bootstrap_datepicker_plus",
'django_filters',
'advanced_filters',
'more_admin_filters',
"django_charting",
'timeline',https://github.com/andywar65/timeline
Password validation
https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators
Database
https://docs.djangoproject.com/en/5.0/ref/settings/#databases
"""
import os
from pathlib import Path
from djangoProject.jasmin import JAZZMIN_SETTINGS
from import_export.formats.base_formats import XLSX, JSON, HTML

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
# Путь до папки с базами данных (на одном уровне с папкой проекта)
DB_DIR = os.path.join(os.path.dirname(BASE_DIR), 'djangoProjectDB')

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-vz5p($d!3(1hw%0!+yd4esaxcg!iz(7nefhh!k@m+-c#o6geu3'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = []

# Application definition

INSTALLED_APPS = [
    # сторонние пакеты
    'django_mptt_admin',
    'mptt',
    'adminactions',
    'django_admin_filters',
    'bootstrapsidebar',
    'django_tables2',
    'django_translate_gettext',
    "django_bootstrap5",
    'import_export',
    'crispy_forms',
    'crispy_bootstrap5',
    'crispy_tailwind',
    'tinymce',
    'django_htmx',
    'jazzmin',
    'admin_form_action',
    'rest_framework',
    'django_select2',
    # пакеты Джанго
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # пакеты Пользователя
    'ProjectTDL',
    'StaticData',
    'ProjectContract',
    'PersonalData',
    'Emails',
]
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
AUTOSAVE_PERIOD =120#minutes
MEDIA_ROOT =r"e:\Проекты Симрус\Переписка"
BACKUP_PATH = folder = os.path.join('e:\\','Проекты Симрус', 'backup')

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
]
CRISPY_ALLOWED_TEMPLATE_PACKS = ('Bootstrap5',)
CRISPY_TEMPLATE_PACK = "Bootstrap5"
ROOT_URLCONF = 'djangoProject.urls'
X_FRAME_OPTIONS = 'SAMEORIGIN'
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'djangoProject.wsgi.application'



DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(DB_DIR, 'db.sqlite3'),  # Полный путь к базе данных по умолчанию
    },
    'personal_db': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(DB_DIR, 'personal_db.sqlite3'),  # Полный путь к personal_db
    }
}

DATABASE_ROUTERS = ['PersonalData.DbRouter.PersonalDataRouter',]


AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/
USE_THOUSAND_SEPARATOR = True
USE_L10N = True
DECIMAL_SEPARATOR = '.'
THOUSAND_SEPARATOR = ' '
NUMBER_GROUPING = 3

LANGUAGE_CODE = 'ru'

LANGUAGES = [
    ('ru', 'Russian'),
    ('en', 'English'),
]

from django.utils import timezone

TIME_ZONE = 'Europe/Moscow'

USE_I18N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static/',
]

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
JAZZMIN_SETTINGS = JAZZMIN_SETTINGS
IMPORT_EXPORT_ESCAPE_HTML_ON_EXPORT = True
IMPORT_EXPORT_FORMATS = [XLSX, JSON, HTML]
FILE_UPLOAD_HANDLERS = ("django_excel.ExcelMemoryFileUploadHandler",
                        "django_excel.TemporaryExcelFileUploadHandler")

DJANGO_TABLES2_TABLE_ATTRS = {
    'class': 'table table-striped table-bordered',
    'thead': {
        'class': 'table-light',
    },
}

TINYMCE_DEFAULT_CONFIG = {

}
