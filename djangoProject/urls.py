
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import path, include, re_path
from django.views.generic import TemplateView
from django.contrib.auth import views as auth_views
from django.contrib.admin import site
import adminactions.actions as actions
from django.views.static import serve

from Emails.ЕmailParser.EmailConfig import E_MAIL_DIRECTORY

# register all adminactions
actions.add_to_site(site)

urlpatterns = [
    path("", include('ProjectTDL.urls')),
    path('grappelli/', include('grappelli.urls')),  # grappelli URLS
    path('grappelli-docs/', include('grappelli.urls_docs')),  # grappelli docs URLS
    path("contract/", include("ProjectContract.urls")),
    path("emails/", include("Emails.urls")),
    path('tinymce/', include('tinymce.urls')),
    path("select2/", include("django_select2.urls")),
    path('advanced_filters/', include('advanced_filters.urls')),
    path('admin/', admin.site.urls),
    path('adminactions/', include('adminactions.urls')),
    path('demo', TemplateView.as_view(template_name="bootstrap_base.html"), name='demo'),
    path('popovers', TemplateView.as_view(template_name="bootstrap_popovers.html"), name="popovers"),
    path('login', auth_views.LoginView.as_view(), name="login"),
    path('email-ui/', include('email_ui.urls')),
    re_path(r'^email-files/(?P<path>.*)$', login_required(serve), {
        'document_root': E_MAIL_DIRECTORY
    }),
]

