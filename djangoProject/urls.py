
import os

from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import path, include, re_path
from django.contrib.auth import views as auth_views
from django.contrib.admin import site
import adminactions.actions as actions
from django.views.static import serve

from Emails.ЕmailParser.EmailConfig import E_MAIL_DIRECTORY
from DocRegistry.admin_sites import k1_site, m1_site
from djangoProject.dashboard import dashboard
from djangoProject.health import healthz

# register all adminactions except selected-items export
# (Export as CSV/XLS/fixture убран из меню действий — выгрузки делаются
# штатными отчётами/xlsx-кнопками модулей, а не сырым дампом выборки).
actions.add_to_site(site, exclude=[
    'export_as_csv', 'export_as_xls', 'export_as_fixture',
    'merge',  # склейка записей: на реестрах не используется, только смущает
])

urlpatterns = [
    path('healthz/', healthz, name='healthz'),
    # Алиас для внешних мониторов, опрашивающих /health (иначе 404 каждые 30с)
    path('health/', healthz, name='health'),
    path('health', healthz),
    path('dashboard/', dashboard, name='dashboard'),
    path("", include('ProjectTDL.urls')),
    path('grappelli/', include('grappelli.urls')),  # grappelli URLS
    path('grappelli-docs/', include('grappelli.urls_docs')),  # grappelli docs URLS
    path("contract/", include("ProjectContract.urls")),
    path("api/v1/", include("ProjectContract.api_urls")),
    path("api/docs/", include("DocRegistry.urls")),
    path("docs/", include("DocRegistry.ui_urls")),
    path("emails/", include("Emails.urls")),
    path('tinymce/', include('tinymce.urls')),
    path("select2/", include("django_select2.urls")),
    path('advanced_filters/', include('advanced_filters.urls')),
    path('admin/', admin.site.urls),
    path('admin-m1/', m1_site.urls),  # панель реестра М1
    path('admin-k1/', k1_site.urls),  # панель реестра К1
    path('adminactions/', include('adminactions.urls')),
    path('login', auth_views.LoginView.as_view(), name="login"),
    path('email-ui/', include('email_ui.urls')),
    path('telegram/', include('TelegramParser.urls')),
    re_path(r'^email-files/(?P<path>.*)$', login_required(serve), {
        'document_root': E_MAIL_DIRECTORY
    }),
    re_path(r'^media/(?P<path>.*)$', serve, {
        'document_root': os.path.dirname(E_MAIL_DIRECTORY)
    }),
]

