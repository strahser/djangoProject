from django import forms
from .models import ContractPayments


class ContractPaymentsAdminForm(forms.ModelForm):
    class Meta:
        model = ContractPayments
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data['use_custom_formula']:
            if not cleaned_data['custom_formula']:
                self.add_error(
                    'custom_formula',
                    'Введите формулу, если вы хотите использовать пользовательский расчет.'
                )
            if not cleaned_data['field_to_overwrite']:
                self.add_error(
                    'field_to_overwrite',
                    'Выберите поле для перезаписи.'
                )

        return cleaned_data


class ContractPaymentsForm(forms.ModelForm):
    class Meta:
        model = ContractPayments
        fields = '__all__'
