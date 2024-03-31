# -*- coding: utf-8 -*-

from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Submit, HTML, Button, Row, Field, Column
from crispy_forms.bootstrap import AppendedText, PrependedText, FormActions
from ProjectTDL.models import Task, SubTask, Email


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = '__all__'
        widgets = {
            'due_date': forms.DateInput(
                attrs={'type': 'date',
                       'class': 'form-control',
                       'placeholder': "Date",
                       'onfocus': "(this.type='date')",
                       'onblur': "if(this.value==''){this.type='text'}"

                       }
            )
        }


class EmailForm(forms.ModelForm):
    helper = FormHelper()
    helper.form_method = 'POST'
    helper.add_input(Submit('create_folder', "Создать Каталог", css_class='btn-success'))
    helper.add_input(Submit('save_attachments', 'Сохранить вложения', css_class='btn-primary'))

    class Meta:
        model = Email
        fields = ['project_site', 'contractor', 'email_type', 'name', 'parent']


def selectivity_default_widget(qs, label: str, field_name=None, _choices=None):
    if field_name:
        _choices = sorted(set(
            [(getattr(val, field_name).name, getattr(val, field_name).name) for val in qs]
        ))
    else:
        _choices = _choices
    return forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple(),
                                     label=label,
                                     choices=_choices,
                                     initial=(c[0] for c in _choices),
                                     required=False,
                                     )


class TaskFilterForm(forms.Form):
    qs = Task.objects.all()
    project_site = selectivity_default_widget(qs,'Площадка', 'project_site')
    sub_project = selectivity_default_widget(qs,'Проект', 'sub_project')
    status = selectivity_default_widget(qs,'Статус', 'status')
    contractor_choices = set([(val.contractor, val.contractor) for val in qs if val.contractor])
    contractor = selectivity_default_widget(qs,'Ответсв.', _choices=contractor_choices)
    helper = FormHelper()
    helper.form_method = 'POST'
    helper.form_class = 'form-vertical'
    helper.label_class = 'col-lg-4'
    helper.field_class = 'col-lg-4'
    helper.add_input(Submit('submit', 'Подтвердить', css_class='btn-primary'))
    helper.layout = Layout(
        Row(
            Column('project_site'),
            Column('sub_project'),
            Column('status'),
            Column('contractor'),
        )
    )
