# Generated manually
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('TelegramParser', '0002_category_alter_telegrammessage_tags_tag_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='telegrammessage',
            name='content_path',
            field=models.CharField(blank=True, default='', max_length=500, verbose_name='Путь к файлу контента'),
        ),
        migrations.AlterField(
            model_name='telegrammessage',
            name='text',
            field=models.TextField(blank=True, default='', verbose_name='Текст'),
        ),
        migrations.AlterField(
            model_name='telegrammessage',
            name='html_text',
            field=models.TextField(blank=True, default='', verbose_name='Текст (HTML)'),
        ),
    ]
