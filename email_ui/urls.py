from django.urls import path
from email_ui import views

app_name = 'email_ui'

urlpatterns = [
    # --- Inbox / Email list ---
    path('', views.inbox_view, {'folder': 'inbox'}, name='inbox_default'),
    path('folder/<str:folder>/', views.inbox_view, name='inbox'),
    path('partial/', views.email_list_partial, name='email_list_partial'),
    path('unread-count/', views.unread_count, name='unread_count'),

    # --- Email detail / body ---
    path('email/<int:pk>/', views.email_detail, name='email_detail'),
    path('email/<int:pk>/modal/', views.email_detail_modal, name='email_detail_modal'),
    path('email/<int:pk>/body/', views.email_body, name='email_body'),
    path('email/<int:pk>/mark-read/', views.mark_email_as_read, name='mark_email_as_read'),
    path('email/<int:pk>/attachments-modal/', views.attachments_modal, name='attachments_modal'),
    path('email/<int:pk>/open-folder/', views.open_attachment_folder, name='open_attachment_folder'),
    path('email/<int:pk>/thread/', views.email_thread, name='email_thread'),

    # --- Metadata ---
    path('email/<int:pk>/edit-metadata/', views.edit_metadata, name='edit_metadata'),
    path('email/<int:pk>/edit-metadata-form/', views.edit_metadata_form, name='edit_metadata_form'),
    path('email/<int:pk>/metadata-display/', views.metadata_display, name='metadata_display'),

    # --- Folder / Bulk actions ---
    path('email/<int:pk>/add-attachment/', views.add_attachment, name='add_attachment'),
    path('email/<int:pk>/move-to-folder/', views.move_to_folder, name='move_to_folder'),
    path('bulk-action/', views.bulk_action, name='bulk_action'),

    # --- Attachments ---
    path('attachment/<int:att_id>/download/', views.download_attachment, name='download_attachment'),

    # --- Filtering ---
    path('filter-form/partial/', views.filter_form_partial, name='filter_form_partial'),
    path('filter-field-modal/<str:field_name>/', views.filter_field_modal, name='filter_field_modal'),

    # --- Phase 2: Compose & Send ---
    path('compose/', views.compose_modal, name='compose_modal'),
    path('email/<int:pk>/reply/<str:reply_type>/', views.reply_modal, name='reply_modal'),
    path('send/', views.send_email, name='send_email'),
    path('email/<int:pk>/reply-send/', views.reply_send, name='reply_send'),
    path('save-draft/', views.save_draft, name='save_draft'),

    # --- Phase 7: Contacts ---
    path('contacts/', views.contact_list, name='contact_list'),
    path('contacts/<int:pk>/', views.contact_detail, name='contact_detail'),
    path('contacts/create-modal/', views.contact_create_modal, name='contact_create_modal'),
    path('contacts/create/', views.contact_create, name='contact_create'),
    path('contacts/<int:pk>/edit-modal/', views.contact_edit_modal, name='contact_edit_modal'),
    path('contacts/<int:pk>/edit/', views.contact_edit, name='contact_edit'),
    path('contacts/<int:pk>/delete/', views.contact_delete, name='contact_delete'),
    path('contacts/search/', views.contact_search, name='contact_search'),

    # --- Phase 3: Tags ---
    path('tags/', views.tag_list, name='tag_list'),
    path('tags/create-modal/', views.tag_create_modal, name='tag_create_modal'),
    path('tags/create/', views.tag_create, name='tag_create'),
    path('tags/<int:pk>/delete/', views.tag_delete, name='tag_delete'),
    path('tags/assign/', views.assign_tag, name='assign_tag'),
    path('tags/<int:email_id>/remove/<int:tag_id>/', views.remove_tag, name='remove_tag'),
    path('tags/bulk-assign/', views.bulk_assign_tag, name='bulk_assign_tag'),
    path('email/<int:pk>/toggle-important/', views.toggle_important, name='toggle_important'),

    # --- Phase 4: Email ↔ Task ---
    path('link-to-task/', views.link_email_to_task, name='link_email_to_task'),
    path('unlink-from-task/<int:link_id>/', views.unlink_email_from_task, name='unlink_email_from_task'),
    path('email/<int:pk>/create-task/', views.create_task_from_email, name='create_task_from_email'),
    path('email/<int:pk>/copy-email/', views.copy_email, name='copy_email'),
    path('email/<int:pk>/attach-to-tasks-modal/', views.attach_to_tasks_modal, name='attach_to_tasks_modal'),
    path('email/<int:pk>/attach-tasks/', views.attach_tasks, name='attach_tasks'),
    path('email/<int:pk>/detach-task/<int:task_id>/', views.detach_task, name='detach_task'),

    # --- Phase 6: Export ---
    path('export-modal/', views.export_modal, name='export_modal'),
    path('export/', views.do_export, name='do_export'),

    # --- Phase 3: Saved Filters ---
    path('saved-filters/', views.saved_filters_list, name='saved_filters_list'),
    path('saved-filters/save/', views.save_current_filter, name='save_current_filter'),
    path('saved-filters/<int:pk>/apply/', views.apply_saved_filter, name='apply_saved_filter'),
    path('saved-filters/<int:pk>/delete/', views.delete_saved_filter, name='delete_saved_filter'),

    # --- Phase 8: Automation Rules ---
    path('rules/', views.rules_list, name='rules_list'),
    path('rules/create-modal/', views.rule_create_modal, name='rule_create_modal'),
    path('rules/create/', views.rule_create, name='rule_create'),
    path('rules/<int:pk>/edit-modal/', views.rule_edit_modal, name='rule_edit_modal'),
    path('rules/<int:pk>/edit/', views.rule_edit, name='rule_edit'),
    path('rules/<int:pk>/toggle/', views.rule_toggle, name='rule_toggle'),
    path('rules/<int:pk>/run-now/', views.rule_run_now, name='rule_run_now'),

    # --- Fetch emails (existing) ---
    path('fetch-emails/', views.fetch_emails, name='fetch_emails'),
]
