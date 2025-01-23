# -*- coding: utf-8 -*-

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column
from django import forms
from django.forms import ModelForm
from loguru import logger
from ProjectTDL.models import Task


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


class TaskAdminUpdateDate(forms.Form):
    helper = FormHelper()
    due_date = forms.DateField(label='Выберите дату завершения')
    due_date.widget = forms.widgets.DateInput(attrs={'type': 'date',
                                                     'class': 'form-control',
                                                     'placeholder': "Date",
                                                     'onfocus': "(this.type='date')",
                                                     'onblur': "if(this.value==''){this.type='text'}"

                                                     })

    # helper.add_input(Submit('submit', "Подтвердить", css_class='btn-success'))

    def update_due_date(self, task: Task):
        task.due_date = self.cleaned_data['due_date']
        task.save()


class TaskUpdateValuesForm(ModelForm):
    due_date = forms.DateField(label='Выберите дату завершения')
    due_date.widget = forms.widgets.DateInput(attrs={'type': 'date',
                                                     'class': 'form-control',
                                                     'placeholder': "Date",
                                                     'onfocus': "(this.type='date')",
                                                     'onblur': "if(this.value==''){this.type='text'}"
                                                     })

    class Meta:
        model = Task
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(TaskUpdateValuesForm, self).__init__(*args, **kwargs)

        for key in self.fields:
            self.fields[key].required = False

    helper = FormHelper()
    helper.form_method = 'POST'
    helper.add_input(Submit('submit', 'Подтвердить', css_class='btn-success'))


class TaskAdminUpdate(forms.Form):
    price = forms.FloatField()

    def update_price(self, task: Task):
        task.price = self.cleaned_data['price']
        task.save()

def select_default_widget(qs, label: str, field_name:str, _choices=None):
    """возвращает MultipleChoiceField для заданного qs field_name возвращает pk, label для выбора  """
    _choices_list = []
    if not _choices:
        for val in qs:
            try:
                field_value = getattr(val, field_name)
                if field_value:
                    temp = field_value.pk, field_value.name
                    _choices_list.append(temp)
            except Exception as e:
                logger.exception(e)
    else:
        _choices_list = _choices
    return forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple(),
                                     label=label,
                                     choices=set(_choices_list),
                                     required=False,
                                     )


class TaskFilterForm(forms.Form):
    qs = Task.objects.all()
    project_site = select_default_widget(qs, 'Площадка', 'project_site')
    sub_project = select_default_widget(qs, 'Проект', 'sub_project')
    status = select_default_widget(qs, 'Статус', 'status')
    category = select_default_widget(qs, 'Категория', 'category')
    contractor = select_default_widget(qs, 'Ответсв.', 'contractor')
    building_number = select_default_widget(qs, 'Здание', 'building_number')
    due_date = forms.ChoiceField(
        widget=forms.Select,
        choices=[('', ''),
                 ('today', 'Сегодня'),
                 ('week', 'Эта Неделя'),
                 ('past', 'просроченные')
                 ],
        required=False,
        label="Окончание",
    )
    helper = FormHelper()
    helper.form_class = 'form-vertical'
    helper.label_class = 'col-lg-7'
    helper.field_class = 'col-lg-7'
    helper.add_input(Submit('submit', 'Обновить', css_class='btn-success'))
    helper.add_input(Submit('save_attachments', 'Экспорт в ексель', css_class='btn-primary'))
    helper.layout = Layout(
        Row(
            Column('project_site'),
            Column('sub_project'),
            Column('status'),
            Column('category'),
            Column('contractor'),
            Column('due_date'),
        )
    )

    @staticmethod
    def update_contractor_form(df_initial, _filter_form) -> forms.Form:
        _contractor_choices = [(val, val) for val in df_initial['contractor'].unique() if val]
        contractor = forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple(),
                                               label='Ответсв.',
                                               choices=_contractor_choices,
                                               initial=(c[0] for c in _contractor_choices),
                                               required=False,
                                               )
        _filter_form.fields["contractor"] = contractor
        return _filter_form



class TaskUpdateForm(forms.ModelForm):
    helper = FormHelper()
    # helper.form_method = 'POST'
    helper.add_input(Submit('submit', "Подтвердить"))

    class Meta:
        model = Task
        fields = '__all__'


class ScaleForm(forms.Form):
    scale = forms.ChoiceField(
        choices=[
            ('day', 'День'),
            ('week', 'Неделя'),
            ('month', 'Месяц'),
            ('quarter', 'Квартал'),
        ],
        initial='day',
    )
