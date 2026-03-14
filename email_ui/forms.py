from django import forms

from Emails.models import Email, InfoChoices  # Добавлен импорт InfoChoices
from ProjectContract.models import Contractor
from StaticData.models import ProjectSite, Category, BuildingType


class EmailFilterForm(forms.Form):
    search = forms.CharField(
        required=False,
        label='Поиск',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Поиск...'})
    )
    project_site = forms.ModelMultipleChoiceField(
        queryset=ProjectSite.objects.all(),
        required=False,
        label='Проекты',
        widget=forms.SelectMultiple(attrs={'class': 'form-select'})
    )
    contractor = forms.ModelMultipleChoiceField(
        queryset=Contractor.objects.all(),
        required=False,
        label='Подрядчики',
        widget=forms.SelectMultiple(attrs={'class': 'form-select'})
    )
    category = forms.ModelMultipleChoiceField(
        queryset=Category.objects.all(),
        required=False,
        label='Категории',
        widget=forms.SelectMultiple(attrs={'class': 'form-select'})
    )
    building_type = forms.ModelMultipleChoiceField(
        queryset=BuildingType.objects.all(),
        required=False,
        label='Здания',
        widget=forms.SelectMultiple(attrs={'class': 'form-select'})
    )
    info = forms.MultipleChoiceField(
        choices=InfoChoices.choices,
        required=False,
        label='Тип информации',
        widget=forms.SelectMultiple(attrs={'class': 'form-select'})
    )
    has_attachments = forms.BooleanField(
        required=False,
        label='С вложениями',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    is_important = forms.BooleanField(
        required=False,
        label='Важные',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    is_unread = forms.BooleanField(
        required=False,
        label='Непрочитанные',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    date_from = forms.DateField(
        required=False,
        label='Дата с',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    date_to = forms.DateField(
        required=False,
        label='Дата по',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.data:
            selected_projects = self.data.getlist('project_site')
            if selected_projects:
                self.fields['contractor'].queryset = Contractor.objects.filter(
                    email__project_site__in=selected_projects
                ).distinct()


class EmailMetadataForm(forms.ModelForm):
    class Meta:
        model = Email
        fields = ['project_site', 'building_type', 'category', 'contractor', 'info', 'is_important']
        widgets = {
            'project_site': forms.Select(attrs={'class': 'form-select'}),
            'building_type': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'contractor': forms.Select(attrs={'class': 'form-select'}),
            'info': forms.Select(attrs={'class': 'form-select'}),
            'is_important': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class TaskSearchForm(forms.Form):
    q = forms.CharField(
        required=False,
        label='Поиск задач',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Название задачи...'})
    )