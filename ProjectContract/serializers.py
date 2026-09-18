from rest_framework import serializers

from .models import Contract, ContractPayments, ContractStageLog


class ContractPaymentsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractPayments
        fields = [
            'id', 'contract', 'name', 'payment_type', 'payment_description',
            'price', 'calc_type', 'percent', 'base_amount',
            'status', 'made_payment', 'paid_amount', 'paid_date',
            'invoice_number', 'start_date', 'due_date', 'duration',
            'creation_stamp', 'update_stamp',
        ]
        read_only_fields = ['id', 'creation_stamp', 'update_stamp']


class ContractStageLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractStageLog
        fields = ['id', 'contract', 'stage', 'date', 'notes', 'is_next_step', 'user']
        read_only_fields = ['id']


class ContractSerializer(serializers.ModelSerializer):
    stage_logs = ContractStageLogSerializer(many=True, read_only=True)

    class Meta:
        model = Contract
        fields = [
            'id', 'project_site', 'contractor', 'client', 'name',
            'number', 'sign_date', 'status', 'stage',
            'next_step', 'next_step_date',
            'parent', 'price', 'estimate',
            'proposal_number', 'proposal_link',
            'start_date', 'duration', 'due_date',
            'stage_logs',
            'creation_stamp', 'update_stamp',
        ]
        read_only_fields = ['id', 'creation_stamp', 'update_stamp']
