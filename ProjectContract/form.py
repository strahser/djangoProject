from django import forms
from .models import ContractPayments


class ContractPaymentsAdminForm(forms.ModelForm):
    class Meta:
        model = ContractPayments
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        calc_type = cleaned_data.get('calc_type') or 'manual'
        if calc_type in ('percent_of_contract', 'percent_of_base') \
                and not cleaned_data.get('percent'):
            self.add_error(
                'percent',
                'Укажите долю (0..1) для процентного расчёта цены.'
            )
        if calc_type == 'percent_of_base' and not cleaned_data.get('base_amount'):
            self.add_error(
                'base_amount',
                'Укажите фиксированную сумму-базу для расчёта доли.'
            )

        return cleaned_data


class ContractPaymentsForm(forms.ModelForm):
    class Meta:
        model = ContractPayments
        fields = '__all__'
