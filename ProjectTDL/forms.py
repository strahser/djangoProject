from django import forms
from bootstrap_datepicker_plus.widgets import DatePickerInput, TimePickerInput, DateTimePickerInput, MonthPickerInput, \
    YearPickerInput
from ProjectTDL.models import Task, Notes


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


class SubtaskForm(forms.ModelForm):
    class Meta:
        model = Notes
        fields = '__all__'
        widgets = {
            'due_date': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'}
            )
        }
