from django.urls import path
from email_ui import views
from email_ui import views_contacts, views_filters, views_rules

app_name = 'email_ui'

urlpatterns = [
    # --- Inbox / Email list ---
    path('', views.inbox_view, {'folder': 'inbox'}, name='inbox_default'),
    path('folder/<str:folder>/', views.inbox_view, name='inbox'),
    path('partial/', views.email_list_partial, name='email_list_partial'),
    path('selection-threads/', views.selection_threads, name='selection_threads'),
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
    path('attachment/<int:att_id>/inline/', views.serve_inline_attachment, name='attachment_inline'),

    # --- Filtering ---
    path('filter-form/partial/', views.filter_form_partial, name='filter_form_partial'),
    path('filter-field-modal/<str:field_name>/', views.filter_field_modal, name='filter_field_modal'),

    # --- Phase 2: Compose & Send ---
    path('compose/', views.compose_modal, name='compose_modal'),
    path('templates/list/', views.template_list, name='template_list'),
    path('templates/<int:pk>/render/', views.template_render, name='template_render'),
    path('email/<int:pk>/reply/<str:reply_type>/', views.reply_modal, name='reply_modal'),
    path('send/', views.send_email, name='send_email'),
    path('email/<int:pk>/reply-send/', views.reply_send, name='reply_send'),
    path('email/<int:pk>/edit-draft/', views.draft_edit, name='draft_edit'),
    path('email/<int:pk>/draft-send/', views.draft_send, name='draft_send'),
    path('email/<int:pk>/draft-update/', views.draft_update, name='draft_update'),
    path('save-draft/', views.save_draft, name='save_draft'),
    path('autosave-draft/', views.autosave_draft, name='autosave_draft'),
    path('email/<int:pk>/copy-to-draft/', views.copy_to_draft, name='copy_to_draft'),

    # --- Contacts / groups / tags (views_contacts) ---
    path('contacts/', views_contacts.contact_list, name='contact_list'),
    path('contacts/<int:pk>/', views_contacts.contact_detail, name='contact_detail'),
    path('contacts/create-modal/', views_contacts.contact_create_modal, name='contact_create_modal'),
    path('contacts/create/', views_contacts.contact_create, name='contact_create'),
    path('contacts/<int:pk>/edit-modal/', views_contacts.contact_edit_modal, name='contact_edit_modal'),
    path('contacts/<int:pk>/edit/', views_contacts.contact_edit, name='contact_edit'),
    path('contacts/<int:pk>/delete/', views_contacts.contact_delete, name='contact_delete'),
    path('contacts/search/', views_contacts.contact_search, name='contact_search'),

    path('groups/', views_contacts.group_list, name='group_list'),
    path('groups/<int:pk>/', views_contacts.group_detail, name='group_detail'),
    path('groups/create-modal/', views_contacts.group_create_modal, name='group_create_modal'),
    path('groups/create/', views_contacts.group_create, name='group_create'),
    path('groups/<int:pk>/edit-modal/', views_contacts.group_edit_modal, name='group_edit_modal'),
    path('groups/<int:pk>/edit/', views_contacts.group_edit, name='group_edit'),
    path('groups/<int:pk>/delete/', views_contacts.group_delete, name='group_delete'),
    path('groups/<int:pk>/add-contact/', views_contacts.group_add_contact, name='group_add_contact'),
    path('groups/<int:pk>/remove-contact/', views_contacts.group_remove_contact, name='group_remove_contact'),
    path('groups/<int:pk>/add-subgroup/', views_contacts.group_add_subgroup, name='group_add_subgroup'),
    path('groups/<int:pk>/remove-subgroup/', views_contacts.group_remove_subgroup, name='group_remove_subgroup'),

    path('tags/', views_contacts.tag_list, name='tag_list'),
    path('tags/create-modal/', views_contacts.tag_create_modal, name='tag_create_modal'),
    path('tags/create/', views_contacts.tag_create, name='tag_create'),
    path('tags/<int:pk>/delete/', views_contacts.tag_delete, name='tag_delete'),
    path('tags/assign/', views_contacts.assign_tag, name='assign_tag'),
    path('tags/<int:email_id>/remove/<int:tag_id>/', views_contacts.remove_tag, name='remove_tag'),
    path('tags/bulk-assign/', views_contacts.bulk_assign_tag, name='bulk_assign_tag'),
    path('email/<int:pk>/toggle-important/', views.toggle_important, name='toggle_important'),

    # --- Phase 4: Email ↔ Task ---
    path('link-to-task/', views.link_email_to_task, name='link_email_to_task'),
    path('unlink-from-task/<int:link_id>/', views.unlink_email_from_task, name='unlink_email_from_task'),
    path('email/<int:pk>/create-task/', views.create_task_from_email, name='create_task_from_email'),
    path('email/<int:pk>/copy-email/', views.copy_email, name='copy_email'),
    path('email/<int:pk>/attach-to-tasks-modal/', views.attach_to_tasks_modal, name='attach_to_tasks_modal'),
    path('email/<int:pk>/attach-tasks-page/', views.attach_tasks_page, name='attach_tasks_page'),
    path('email/<int:pk>/attach-tasks/', views.attach_tasks, name='attach_tasks'),
    path('email/<int:pk>/detach-task/<int:task_id>/', views.detach_task, name='detach_task'),
    path('email/<int:pk>/tasks-partial/', views.email_tasks_partial, name='email_tasks_partial'),

    # --- Phase 6: Export ---
    path('export-modal/', views.export_modal, name='export_modal'),
    path('export/', views.do_export, name='do_export'),

    # --- Saved filters (views_filters) ---
    path('saved-filters/', views_filters.saved_filters_list, name='saved_filters_list'),
    path('saved-filters/modal/', views_filters.saved_filters_modal, name='saved_filters_modal'),
    path('saved-filters/save-modal/', views_filters.save_filter_modal, name='save_filter_modal'),
    path('saved-filters/save/', views_filters.save_current_filter, name='save_current_filter'),
    path('saved-filters/<int:pk>/toggle-pin/', views_filters.toggle_pin_filter, name='toggle_pin_filter'),
    path('saved-filters/<int:pk>/apply/', views_filters.apply_saved_filter, name='apply_saved_filter'),
    path('saved-filters/<int:pk>/delete/', views_filters.delete_saved_filter, name='delete_saved_filter'),

    # --- Automation rules (views_rules) ---
    path('rules/', views_rules.rules_list, name='rules_list'),
    path('rules/create-modal/', views_rules.rule_create_modal, name='rule_create_modal'),
    path('rules/create/', views_rules.rule_create, name='rule_create'),
    path('rules/<int:pk>/edit-modal/', views_rules.rule_edit_modal, name='rule_edit_modal'),
    path('rules/<int:pk>/edit/', views_rules.rule_edit, name='rule_edit'),
    path('rules/<int:pk>/toggle/', views_rules.rule_toggle, name='rule_toggle'),
    path('rules/<int:pk>/run-now/', views_rules.rule_run_now, name='rule_run_now'),

    # --- Fetch emails (existing) ---
    path('fetch-emails/', views.fetch_emails, name='fetch_emails'),

    # --- Настройки отображения почты ---
    path('settings-modal/', views.email_settings_modal, name='email_settings_modal'),
    path('settings-save/', views.save_email_settings, name='save_email_settings'),
]
