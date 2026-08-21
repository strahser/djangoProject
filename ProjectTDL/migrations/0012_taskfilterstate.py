from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ProjectTDL', '0011_alter_projectpin_options_remove_tasknode_sub_project_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='TaskFilterState',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('params', models.JSONField(default=dict, verbose_name='Параметры фильтров')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлено')),
                ('project_site', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='StaticData.projectsite', verbose_name='Проект')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='task_filter_states', to=settings.AUTH_USER_MODEL, verbose_name='Пользователь')),
            ],
            options={
                'verbose_name': 'Сохранённое состояние фильтров',
                'verbose_name_plural': 'Сохранённые состояния фильтров',
                'unique_together': {('user', 'project_site')},
            },
        ),
    ]
