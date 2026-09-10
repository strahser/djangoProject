from django.urls import path

from . import api

urlpatterns = [
    path('intake/', api.intake, name='docs_intake'),
    path('<int:rev_id>/validate/', api.validate, name='docs_validate'),
    path('<int:rev_id>/register/', api.register, name='docs_register'),
    path('<int:rev_id>/remarks/', api.remarks, name='docs_remarks'),
    path('<int:rev_id>/issue/', api.issue, name='docs_issue'),
    path('queue/', api.queue, name='docs_queue'),
    path('entry/<int:code>/', api.entry_card, name='docs_entry'),
]
