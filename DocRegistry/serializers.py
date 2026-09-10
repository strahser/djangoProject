from rest_framework import serializers

from .models import DocRegisterEntry, DocRevision


class DocRegisterEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = DocRegisterEntry
        fields = (
            'id', 'code', 'section', 'building_no', 'cipher', 'file_name',
            'approval_status', 'approval_date', 'submitted_flag', 'change_descr',
            'building_name', 'submit_date', 'acts', 'contractor_new', 'contract',
        )


class DocRevisionSerializer(serializers.ModelSerializer):
    entry_code = serializers.IntegerField(source='entry.code', read_only=True)
    entry_cipher = serializers.CharField(source='entry.cipher', read_only=True)

    class Meta:
        model = DocRevision
        fields = (
            'id', 'entry', 'entry_code', 'entry_cipher', 'rev_no', 'file',
            'sha256', 'size', 'received_at', 'email', 'attachment',
            'source', 'status', 'storage_path', 'archive_path',
            'submitted_folder', 'task', 'accdb_task_code',
        )
