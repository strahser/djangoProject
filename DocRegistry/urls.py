from django.urls import path

from . import api

urlpatterns = [
    path('<str:project>/intake/', api.intake, name='docs_intake'),
    path('<str:project>/<int:rev_id>/validate/', api.validate, name='docs_validate'),
    path('<str:project>/<int:rev_id>/register/', api.register, name='docs_register'),
    path('<str:project>/<int:rev_id>/remarks/', api.remarks, name='docs_remarks'),
    path('<str:project>/<int:rev_id>/issue/', api.issue, name='docs_issue'),
    path('<str:project>/queue/', api.queue, name='docs_queue'),
    path('<str:project>/entry/<int:code>/', api.entry_card, name='docs_entry'),
]
