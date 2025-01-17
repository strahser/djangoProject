
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.contrib.auth import views as auth_views
from django.contrib.admin import site
import adminactions.actions as actions

# register all adminactions
actions.add_to_site(site)


urlpatterns = [
    path('grappelli/', include('grappelli.urls')),  # grappelli URLS
    path('grappelli-docs/', include('grappelli.urls_docs')),  # grappelli docs URLS
    path('admin/', admin.site.urls),
    path("", include('ProjectTDL.urls')),
    path("contract/", include("ProjectContract.urls")),
    path('tinymce/', include('tinymce.urls')),
    path('advanced_filters/', include('advanced_filters.urls')),
    path('adminactions/', include('adminactions.urls')),
    path('demo', TemplateView.as_view(template_name="bootstrap_base.html"), name='demo'),
    path('popovers', TemplateView.as_view(template_name="bootstrap_popovers.html"), name="popovers"),
    path('login', auth_views.LoginView.as_view(), name="login"),


]
