import os

import django_tables2 as tables
from django.http import HttpResponse
from django.urls import reverse_lazy, reverse
from django.utils.safestring import mark_safe
from django_tables2 import LazyPaginator
from pretty_html_table import pretty_html_table

from AdminUtils import get_standard_display_list
from ProjectTDL.models import Task
from services.DataFrameRender.RenderDfFromModel import create_df_from_model, renamed_dict
from services.Downloads.ExcelDownload import df_to_excel_in_memory
import re


def rows_higlighter(**kwargs):
	# Add highlight class to rows
	# when the product is recently updated.
	# Recently updated rows are in the table
	# selection parameter.
	selected_rows = kwargs["table"].selected_rows
	if selected_rows and kwargs["record"].pk in selected_rows:
		return "highlight-me"
	return ""


class TaskTable(tables.Table):
	class CheckBoxColumnWithName(tables.CheckBoxColumn):
		@property
		def header(self):
			return self.verbose_name

	TEMPLATE = '''
    <div class="btn-group" role="group" aria-label="Basic example">
       <a href="{% url TaskUpdateView record.pk %}" class="btn btn-primary btn-success">'📄'</a>
       <a href="{% url TaskDeleteView record.pk %}" class="btn btn-primary btn-danger">X</a>
    </div>
    '''
	name = tables.LinkColumn('TaskUpdateView', args=[tables.A('pk')], default='Link', empty_values=())
	action = tables.TemplateColumn(TEMPLATE, verbose_name='Действия')
	selection = CheckBoxColumnWithName(
		verbose_name=mark_safe('<input type="button" class="form-check-input" id="checkAll">'), accessor="pk",

		orderable=False,
		attrs={
			"td__input": {
				"@click": "checkRange"
			}
		}
		)

	def render_action(self, record):
		clone_url = reverse("TaskCloneView", args=[record.pk])
		del_url = reverse("TaskDeleteView", args=[record.pk])
		return mark_safe(f'''
                    <div class="btn-group" role="group" aria-label="Basic example">
                        <a href="{clone_url}" class="btn btn-primary btn-success">📄</a>
                         <a href="{del_url}" class="btn btn-primary btn-danger">X</a>
                    </div>
                         ''')

	@staticmethod
	def Save_table_django(model, qs, excluding_list=None):
		df_initial = create_df_from_model(model, qs)
		df_export = df_initial \
			.filter(get_standard_display_list(model, excluding_list)) \
			.rename(renamed_dict(Task), axis='columns') \
			.fillna('')
		_buffer = df_to_excel_in_memory([df_export], ['analytics_data'])
		filename = f"Задачи.xlsx"
		res = HttpResponse(
			_buffer.getvalue(),  # Gives the Byte string of the Byte Buffer object
			content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
		)
		res['Content-Disposition'] = f'attachment; filename={filename}'
		# https://likegeeks.com/pandas-to-html-table-styling-css-styler/#Table_Borders_and_Spacing
		desktop = os.path.normpath(os.path.expanduser("~/Desktop"))
		file_path = os.path.join(desktop, 'Задачи.html')
		html_table_blue_light = pretty_html_table.build_table(df_export, 'blue_dark', escape=False, )
		regex = '/ \\n |\\r\\n |\\n\\r |\\r / g'
		html_table_blue_light = re.sub(regex, '<br>', html_table_blue_light)
		# Save to html file
		with open(file_path, 'w') as f:
			f.write(html_table_blue_light)
		return res

	class Meta:
		model = Task
		template_name = "django_tables2/bootstrap.html"
		# template_name = "tables/bootstrap_htmx_bulkaction.html"
		exclude = ("creation_stamp", 'update_stamp', 'contract', 'description', 'owner')
		row_attrs = {
			"data-id": lambda record: record.pk

		}
		attrs = {"id": "TaskTable",
		         'class': 'table table-striped table-bordered',
		         'thead': {
			         'class': 'table-light',
		         },
		         }

		sequence = ("selection", "...")
