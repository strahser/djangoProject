from rest_framework import serializers

from .models import DocRegisterEntry, DocRevision


class DocRegisterEntrySerializer(serializers.ModelSerializer):
    section_name = serializers.SerializerMethodField()
    building_name = serializers.SerializerMethodField()
    building_number = serializers.SerializerMethodField()
    developer_name = serializers.SerializerMethodField()

    class Meta:
        model = DocRegisterEntry
        fields = (
            'id', 'code', 'project', 'section', 'section_name', 'building_no', 'building_number',
            'building', 'building_name', 'cipher', 'file_name',
            'approval_status', 'approval_date', 'submitted_flag', 'change_descr',
            'submit_date', 'acts', 'developer', 'developer_name', 'contract',
        )

    def get_section_name(self, obj):
        return obj.section.short if obj.section else ''

    def get_building_name(self, obj):
        return obj.building.name if obj.building else ''

    def get_building_number(self, obj):
        return obj.building_no.number if obj.building_no else ''

    def get_developer_name(self, obj):
        return obj.developer.name if obj.developer else ''


class DocRevisionSerializer(serializers.ModelSerializer):
    entry_code = serializers.SerializerMethodField()
    entry_cipher = serializers.SerializerMethodField()

    class Meta:
        model = DocRevision
        fields = (
            'id', 'entry', 'entry_code', 'entry_cipher', 'rev_no', 'file',
            'sha256', 'size', 'received_at', 'email', 'attachment',
            'source', 'status', 'storage_path', 'archive_path',
            'submitted_folder', 'task', 'accdb_task_code',
        )

    def get_entry_code(self, obj):
        return obj.entry.code if obj.entry else None

    def get_entry_cipher(self, obj):
        return obj.entry.cipher if obj.entry else ''
