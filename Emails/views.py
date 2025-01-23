import os

from adminactions.utils import flatten
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views import View

from Emails.forms import EmailForm, EmailFilterForm
from Emails.models import Email, EmailType
from ProjectTDL.models import Task
from Emails.ЕmailParser.OutlookEmailCreate import parsing_form_for_e_mail_path, make_folder, process_e_mail, \
    add_form_data_to_data_base
from Emails.ЕmailParser.ParsingImapEmailToDB import ParsingImapEmailToDB


def e_mail_add(request):
    if request.method == 'POST':
        _form = EmailForm(request.POST)
        if 'create_folder' in request.POST and _form.is_valid():
            parsing_form_for_e_mail_path(_form)
            make_folder(_form.cleaned_data['link'])
            return render(request, 'Emails/e_mail_form.html',
                          {'form': _form, 'data_path': _form.cleaned_data['link']})

        if 'save_attachments' in request.POST and _form.is_valid():
            _parsed_form = parsing_form_for_e_mail_path(_form)
            make_folder(_form.cleaned_data['link'])
            parsing_form_data = process_e_mail(_parsed_form, request)
            add_form_data_to_data_base(parsing_form_data, request)
            return render(request, 'Emails/e_mail_form.html',
                          {'form': _form, 'data_path': _form.cleaned_data['link']})
    else:
        _form = EmailForm()
        return render(request, 'Emails/e_mail_form.html', {'form': _form, 'data_path': None})

def handle_incoming_email(request):
    # url_redirect = reverse('admin/Emails/email/')
    if request.method == 'POST':
        email_limit = int(request.POST.get('mail_count'))
        initial_folder_list = {'INBOX': EmailType.IN.name, 'Отправленные': EmailType.OUT.name }
        actions_list = []
        scip_list = []
        directory = os.path.join('e:\Проекты Симрус', 'Переписка', 'imap_attachments')
        for folder, folder_db_name in initial_folder_list.items():
            root_path = os.path.join(directory, folder)
            _parser = ParsingImapEmailToDB(root_path)
            _parser.main(folder_db_name, folder, limit=email_limit)
            actions_list.append(_parser.create_action_list)
            scip_list.append(_parser.skip_action_list)
        actions_list = flatten(actions_list)
        scip_list = flatten(scip_list)
        if actions_list:
            res_list = [str(val) for val in actions_list]
            messages.success(request, f"Почта сохранена Для следующих позиций {res_list}")
        else:
            res_list = [str(val) for val in scip_list]
            messages.info(request, f"Нечего обновлять")
        return redirect('admin:Emails_email_changelist')
    else:
        messages.error(request, "Возникли ошибки")
        return redirect('admin:Emails_email_changelist')


class SelectEmailView(View):
    def get(self, request, task_id):
        senders_list = Email.objects.values_list('sender', flat=True)
        senders = sorted(set(sender for sender in senders_list if sender))
        sender_choices = [(sender, sender) for sender in senders]
        form = EmailFilterForm(request.GET, sender_choices=sender_choices)
        emails = Email.objects.all()
        task = Task.objects.get(pk=task_id)

        if form.is_valid():
            project_site = form.cleaned_data.get('project_site')
            contractor = form.cleaned_data.get('contractor')
            email_type = form.cleaned_data.get('email_type')
            search_query = form.cleaned_data.get('search_query')
            senders = form.cleaned_data.get('sender_choices')

            if project_site:
                emails = emails.filter(project_site=project_site)
            if contractor:
                emails = emails.filter(contractor=contractor)
            if email_type:
                emails = emails.filter(email_type=email_type)
            if senders:
                emails = emails.filter(sender__in=senders)
            if search_query:
                emails = emails.filter(
                    Q(name__icontains=search_query) |
                    Q(subject__icontains=search_query) |
                    Q(sender__icontains=search_query) |
                    Q(receiver__icontains=search_query)
                )

        return render(request, 'Emails/select_email.html', {
            'form': form,
            'emails': emails,
            'task': task,
        })

    def post(self, request, task_id):
        selected_email_ids = request.POST.getlist('selected_emails')
        task = Task.objects.get(pk=task_id)
        emails = Email.objects.filter(id__in=selected_email_ids)
        if 'edit_action' in request.POST:
           edit_url = reverse('edit_email_form')
           return redirect(f'{edit_url}?selected_emails={",".join(selected_email_ids)}&task_id={task_id}')
        else:
            for email in emails:
                email.parent = task
                email.save()
            return redirect('admin:Emails_task_change', task_id)


class EditEmailFormView(View):
    def get(self, request):
       selected_email_ids = request.GET.get('selected_emails', '').split(',')
       selected_email_ids = [email_id.replace(u'\xa0', '') for email_id in selected_email_ids if email_id]
       task_id = request.GET.get('task_id')
       if not selected_email_ids:
            return redirect('select_email', task_id=task_id)
       emails = Email.objects.filter(id__in=selected_email_ids)
       senders_list = Email.objects.values_list('sender', flat=True)
       senders = sorted(set(sender for sender in senders_list if sender))
       sender_choices = [(sender, sender) for sender in senders]
       form = EmailFilterForm(request.GET, sender_choices=sender_choices)
       return render(request, 'Emails/edit_email_form.html', {
          'emails': emails,
           'form':form,
           'task_id': task_id,
            'senders': senders,
         })
    def post(self, request):
        selected_email_ids = request.POST.getlist('selected_emails')
        selected_email_ids = [email_id.replace(u'\xa0', '') for email_id in selected_email_ids]
        task_id=request.POST.get('task_id')
        if selected_email_ids:
            emails = Email.objects.filter(id__in=selected_email_ids)
            if request.POST:
                update_data = {}
                for key, value in request.POST.items():
                    if key.endswith('_checkbox') and value == 'True':
                        field_name = key.replace('_checkbox', '')
                        update_data[field_name] = request.POST.get(field_name)

                if update_data:
                    emails.update(**update_data)
            if emails:
                if emails.first().parent:
                    return redirect('select_email', task_id=emails.first().parent.id)
        return redirect('select_email', task_id=task_id)