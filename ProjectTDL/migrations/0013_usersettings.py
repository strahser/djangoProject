from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ProjectTDL', '0012_taskfilterstate'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('inherit_props', models.BooleanField(default=False, verbose_name='Наследовать свойства от родителя')),
                ('new_task_position', models.CharField(choices=[('top', 'Вверху списка'), ('bottom', 'Внизу списка')], default='bottom', max_length=10, verbose_name='Порядок новых подзадач')),
                ('default_tree_view', models.BooleanField(default=False, verbose_name='Дерево по умолчанию')),
                ('default_project_site', models.BooleanField(default=False, verbose_name='Заполнять проект из контекста')),
                ('default_category', models.BooleanField(default=False, verbose_name='Заполнять категорию из контекста')),
                ('default_status', models.BooleanField(default=False, verbose_name='Заполнять статус из контекста')),
                ('default_contractor', models.BooleanField(default=False, verbose_name='Заполнять ответственного из контекста')),
                ('column_visibility', models.JSONField(default=dict, verbose_name='Видимость колонок')),
                ('auto_save', models.BooleanField(default=True, verbose_name='Сохранять состояние фильтров')),
                ('active_project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='StaticData.projectsite', verbose_name='Активный проект')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='task_user_settings', to=settings.AUTH_USER_MODEL, verbose_name='Пользователь')),
            ],
            options={
                'verbose_name': 'Настройки пользователя',
                'verbose_name_plural': 'Настройки пользователей',
            },
        ),
    ]
