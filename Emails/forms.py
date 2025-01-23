# -*- coding: utf-8 -*-

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from django import forms

from Emails.models import Email, EmailType
from ProjectContract.models import Contractor
from StaticData.models import ProjectSite


class EmailFilterForm(forms.Form):
    project_site = forms.ModelChoiceField(
        queryset=ProjectSite.objects.all(),
        required=False,
        label='Проект',
        empty_label="Все"
    )
    contractor = forms.ModelChoiceField(
        queryset=Contractor.objects.all(),
        required=False,
        label='Подрядчик',
        empty_label="Все"
    )
    email_type = forms.ChoiceField(
        choices=[('', 'Все')] + list(EmailType.choices()),
        required=False,
        label='Тип'
    )
    sender_choices = forms.MultipleChoiceField(
        required=False,
        label='Отправитель',
        widget=forms.SelectMultiple(attrs={'class':'form-control multi-select'})

    )


    search_query = forms.CharField(required=False, label='Поиск')



    def __init__(self, *args, **kwargs):
        sender_choices = kwargs.pop('sender_choices', [])
        super().__init__(*args, **kwargs)
        self.fields['sender_choices'].choices = sender_choices



class EmailForm(forms.ModelForm):
    helper = FormHelper()
    helper.form_method = 'POST'
    helper.add_input(Submit('create_folder', "Создать Каталог", css_class='btn-success'))
    helper.add_input(Submit('save_attachments', 'Сохранить вложения', css_class='btn-primary'))

    class Meta:
        model = Email
        fields = ['project_site', 'contractor', 'email_type', 'name', 'parent']

