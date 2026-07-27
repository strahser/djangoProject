# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Emails', '0005_remove_attachment_unique_together'),
    ]

    operations = [
        migrations.AddField(
            model_name='email',
            name='sender_name',
            field=models.CharField(blank=True, default='', max_length=200, verbose_name='Имя отправителя'),
        ),
    ]
