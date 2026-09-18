from rest_framework import serializers

_serializer_cache: dict = {}


def _serializer_for(base, model, fields):
    key = (base.__name__, model.__name__)
    if key not in _serializer_cache:
        meta = type('Meta', (), {'model': model, 'fields': fields})
        _serializer_cache[key] = type(
            f'{model.__name__}{base.__name__}', (base,), {'Meta': meta})
    return _serializer_cache[key]


class BaseRegistryEntrySerializer(serializers.ModelSerializer):
    section_name = serializers.SerializerMethodField()
    building_name = serializers.SerializerMethodField()
    building_number = serializers.SerializerMethodField()
    developer_name = serializers.SerializerMethodField()
    project = serializers.SerializerMethodField()

    class Meta:
        model = None
        fields = (
            'id', 'code', 'project', 'section', 'section_name', 'building_no', 'building_number',
            'building', 'building_name', 'cipher', 'file_name',
            'approval_status', 'approval_date', 'submitted_flag', 'change_descr',
            'submit_date', 'acts', 'developer', 'developer_name', 'contract',
        )

    def get_project(self, obj):
        return obj.PROJECT_CODE

    def get_section_name(self, obj):
        return obj.section.short if obj.section else ''

    def get_building_name(self, obj):
        return obj.building.name if obj.building else ''

    def get_building_number(self, obj):
        return obj.building_no.number if obj.building_no else ''

    def get_developer_name(self, obj):
        return obj.developer.name if obj.developer else ''


class BaseRegistryRevisionSerializer(serializers.ModelSerializer):
    entry_code = serializers.SerializerMethodField()
    entry_cipher = serializers.SerializerMethodField()

    class Meta:
        model = None
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


def entry_serializer_for(model):
    """Сериализатор записи под конкретную таблицу реестра (M1Entry/K1Entry)."""
    return _serializer_for(
        BaseRegistryEntrySerializer, model, BaseRegistryEntrySerializer.Meta.fields)


def revision_serializer_for(model):
    """Сериализатор ревизии под конкретную таблицу (M1Revision/K1Revision)."""
    return _serializer_for(
        BaseRegistryRevisionSerializer, model, BaseRegistryRevisionSerializer.Meta.fields)
