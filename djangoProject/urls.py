"""
URL configuration for djangoProject project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.template.defaulttags import url
from django.urls import path, include, re_path
from django.views.generic import TemplateView
from django.contrib.auth import views as auth_views
from django.contrib.admin import site
import adminactions.actions as actions

# register all adminactions
# actions.add_to_site(site)

urlpatterns = [
    path('admin/', admin.site.urls),
    path("", include('ProjectTDL.urls')),
    path('tinymce/', include('tinymce.urls')),
    path('advanced_filters/', include('advanced_filters.urls')),
    path('adminactions/', include('adminactions.urls')),


    path('demo', TemplateView.as_view(template_name="bootstrap_base.html"), name='demo'),
    path('popovers', TemplateView.as_view(template_name="bootstrap_popovers.html"), name="popovers"),
    path('login', auth_views.LoginView.as_view(), name="login"),

]
