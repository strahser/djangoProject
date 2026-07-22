from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from AdminUtils import get_standard_display_list, duplicate_event
from .models import TelegramChannel, TelegramMessage, ParseLog, Tag, Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'slug', 'tag_count')
    search_fields = ('name',)
    list_per_page = 30
    actions = [duplicate_event]

    @admin.display(description='Тегов')
    def tag_count(self, obj):
        return obj.tag_set.count()


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'category', 'message_count')
    list_filter = ('category',)
    search_fields = ('name',)
    list_per_page = 50
    actions = [duplicate_event]

    @admin.display(description='Сообщений')
    def message_count(self, obj):
        return obj.telegrammessage_set.count()


@admin.register(TelegramChannel)
class TelegramChannelAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'username', 'is_active', 'last_parsed',
                    'message_count', 'fetch_button', 'creation_stamp')
    list_filter = ('is_active',)
    search_fields = ('name', 'username')
    list_per_page = 20
    actions = [duplicate_event]
    change_list_template = 'TelegramParser/telegramchannel_changelist.html'

    @admin.display(description='Сообщений')
    def message_count(self, obj):
        return obj.telegrammessage_set.count()

    @admin.display(description='Действие')
    def fetch_button(self, obj):
        url = reverse('TelegramParser:fetch_channel_data', args=[obj.pk])
        return format_html(
            '<a class="btn btn-sm btn-success" href="{}" '
            'onclick="return confirm(\'Получить новые данные с канала {}?\')">'
            'Получить данные</a>',
            url, obj.name
        )


@admin.register(TelegramMessage)
class TelegramMessageAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'channel_name', 'author', 'text_short', 'date',
        'importance_badge', 'total_reactions', 'categories_display', 'source'
    )
    list_filter = (
        'importance', 'channel_name', 'source', 'has_media', 'is_pinned',
        'tag_objects__category', 'tag_objects',
    )
    search_fields = ('text', 'author', 'tags')
    filter_horizontal = ('tag_objects',)
    readonly_fields = (
        'telegram_id', 'importance', 'total_reactions',
        'creation_stamp', 'update_stamp'
    )
    list_per_page = 25
    actions = [duplicate_event]

    @admin.display(description='Текст')
    def text_short(self, obj):
        if not obj.text:
            return '(медиа)'
        return obj.text[:100] + '...' if len(obj.text) > 100 else obj.text

    @admin.display(description='Важность', ordering='importance')
    def importance_badge(self, obj):
        colors = {1: 'secondary', 2: 'info', 3: 'warning', 4: 'danger'}
        color = colors.get(obj.importance, 'secondary')
        label = obj.get_importance_display()
        return format_html('<span class="badge bg-{}">{}</span>', color, label)


@admin.register(ParseLog)
class ParseLogAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'channel', 'operation', 'started_at', 'finished_at',
        'messages_found', 'messages_saved', 'messages_skipped', 'status'
    )
    list_filter = ('status', 'operation')
    readonly_fields = ('started_at',)
    list_per_page = 20
