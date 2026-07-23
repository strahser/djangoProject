from django import forms

from Emails.models import Email, InfoChoices
from ProjectContract.models import Contractor
from StaticData.models import ProjectSite, Category, BuildingType
from .models import Contact, ContactEmail, EmailTag, EmailTemplate, EmailRule, SMTPAccount, SavedFilter


class EmailFilterForm(forms.Form):
    search = forms.CharField(
        required=False,
        label='Поиск',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Поиск...'})
    )
    sender = forms.CharField(
        required=False,
        label='Отправитель',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Выберите отправителя...', 'list': 'sender-datalist', 'autocomplete': 'off'})
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
    tags = forms.ModelMultipleChoiceField(
        queryset=EmailTag.objects.all(),
        required=False,
        label='Теги',
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
    folder = forms.ChoiceField(
        choices=[('', 'Все папки')] + Email.FOLDER_CHOICES,
        required=False,
        label='Папка',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    sent_status = forms.ChoiceField(
        choices=[('', 'Все')] + [
            ('draft', 'Черновик'), ('queued', 'В очереди'),
            ('sent', 'Отправлено'), ('failed', 'Ошибка'),
        ],
        required=False,
        label='Статус отправки',
        widget=forms.Select(attrs={'class': 'form-select'})
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


class ComposeEmailForm(forms.Form):
    to = forms.CharField(
        required=False,
        label='Кому',
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': 'email1@example.com, email2@example.com',
            'data-role': 'tagsinput'
        })
    )
    cc = forms.CharField(
        required=False,
        label='Копия',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'email@example.com'})
    )
    bcc = forms.CharField(
        required=False,
        label='Скрытая копия',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'email@example.com'})
    )
    subject = forms.CharField(
        label='Тема',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Тема письма'})
    )
    body = forms.CharField(
        label='Текст письма',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 15, 'id': 'compose-body'}),
    )
    template = forms.ModelChoiceField(
        queryset=EmailTemplate.objects.all(),
        required=False,
        label='Шаблон',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'template-select'}),
    )
    smtp_account = forms.ModelChoiceField(
        queryset=SMTPAccount.objects.filter(is_active=True),
        required=False,
        label='Аккаунт отправки',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    use_outlook = forms.BooleanField(
        required=False,
        label='Отправить через Outlook',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )


class ComposeReplyForm(ComposeEmailForm):
    include_attachments = forms.BooleanField(
        required=False,
        initial=True,
        label='Отправить с вложением',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop('template', None)
        self.fields.pop('smtp_account', None)
        self.fields.pop('use_outlook', None)
        self.fields.pop('bcc', None)


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ['name', 'company', 'position', 'phone', 'notes', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'company': forms.Select(attrs={'class': 'form-select'}),
            'position': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ContactEmailForm(forms.ModelForm):
    class Meta:
        model = ContactEmail
        fields = ['email', 'label', 'is_primary']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'label': forms.Select(attrs={'class': 'form-select'}),
            'is_primary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class EmailTagForm(forms.ModelForm):
    class Meta:
        model = EmailTag
        fields = ['name', 'color', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class EmailRuleForm(forms.ModelForm):
    class Meta:
        model = EmailRule
        fields = ['name', 'description', 'is_active', 'priority', 'conditions', 'actions']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'priority': forms.NumberInput(attrs={'class': 'form-control'}),
            'conditions': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'data-editor': 'json'}),
            'actions': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'data-editor': 'json'}),
        }


class ExportForm(forms.Form):
    FORMAT_CHOICES = [
        ('copy', 'Копировать папку'),
        ('eml', 'EML (RFC 822)'),
        ('html', 'HTML'),
        ('mbox', 'MBOX'),
    ]
    ORGANIZE_CHOICES = [
        ('date', 'По дате'),
        ('sender', 'По отправителю'),
        ('project', 'По проекту'),
    ]
    export_format = forms.ChoiceField(
        choices=FORMAT_CHOICES,
        initial='copy',
        label='Формат',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    organize_by = forms.ChoiceField(
        choices=ORGANIZE_CHOICES,
        initial='date',
        label='Структура папок',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    include_attachments = forms.BooleanField(
        required=False,
        initial=True,
        label='Включая вложения',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )


class SavedFilterForm(forms.ModelForm):
    class Meta:
        model = SavedFilter
        fields = ['name', 'folder', 'is_default', 'is_shared']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'folder': forms.Select(attrs={'class': 'form-select'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_shared': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }