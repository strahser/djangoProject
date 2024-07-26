from datetime import datetime
from functools import reduce
import pandas as pd
from dataclasses import dataclass, asdict
from django.db import models
from django.shortcuts import render
from django.urls import reverse
from AdminUtils import get_standard_display_list
import humanize

HTML_DF_PROPERTY = dict(
	classes="table table-striped table-bordered",
	table_id='TaskTable',
	index=False,
	show_dimensions=True,
	render_links=True,
	justify='center',
	escape=False
)
PIVOT_HTML_PROPERTY = dict(
	classes="table table-bordered",
	table_id='TaskTable',
	index=True,
	show_dimensions=False,
	render_links=True,
	justify='center',
	escape=False,
	na_rep='-',
)


def create_df_from_model(model, qs, skip_time_stamps: bool = True) -> pd.DataFrame:
	df_dict = {}
	for name in get_standard_display_list(model, skip_time_stamps=skip_time_stamps):
		df_dict[name] = [getattr(val, name) for val in qs]
	return pd.DataFrame(df_dict)


def renamed_dict(model_type, skip_time_stamps=True) -> dict[str, str]:
	"""переименовываем столбцы модели django согласно заданному verbose name """
	names = get_standard_display_list(model_type, skip_time_stamps=skip_time_stamps)
	res_dict = {}
	for val in names:
		try:
			res_dict[val] = model_type._meta.get_field(val).verbose_name
		except:
			pass
	return res_dict


def CloneRecord(queryset):
	for object in queryset:
		object.id = None
		object.save()


@dataclass
class ButtonData:
	url: str
	pk_name: str = 'pk'
	cls: str = 'info'
	name: str = 'изменить'

	def dict(self) -> dict[str, str]:
		return {k: str(v) for k, v in asdict(self).items()}

	def get_reverse_url(self, pk):
		return reverse(self.url, kwargs={self.pk_name: pk})

	def button_link(self, pk) -> str:
		return f'<a href="{self.get_reverse_url(pk)}"class="btn btn-{self.cls} mr-5"   role="button">{self.name}</a>'

	def create_text_link(self, pk, link_text_name: str):
		return str(f"<a href='{self.get_reverse_url(pk)}'>{link_text_name}</a>")

	def create_reverse_button(self, pk):
		res = self.button_link(pk)
		if res:
			return res
		else:
			return ""


def create_group_button(button_list: list[str]) -> str:
	concat_button = reduce(lambda x, y: x + y, button_list)
	return '<div class="btn-group" role="group" aria-label="btn-group">' + concat_button + '</div>'


def create_filtered_df_html(model):
	excluding_list = ['description', 'contract']
	display_list = get_standard_display_list(model, additional_list=['действия'], excluding_list=excluding_list)
	df_initial = model.get_df_render_from_qs()
	df_html_render_page = df_initial. \
		filter(display_list). \
		fillna('-'). \
		rename(renamed_dict(model), axis='columns'). \
		to_html(**HTML_DF_PROPERTY)
	return df_initial, df_html_render_page


def df_html_represented(request, model, df_initial, display_list, _filter_form):
	return render(request, 'ProjectTDL/index.html',
	              {
		              'df': df_initial.
		          filter(display_list)
		          .fillna('-') \
		          .rename(renamed_dict(model), axis='columns') \
		          .to_html(**HTML_DF_PROPERTY),
		              'form': _filter_form
	              }
	              )


def create_df_data_filter_choices(request, _df) -> pd.Series():
	get_date = request.POST.get('due_date')
	_today = pd.to_datetime(datetime.today())
	if get_date:
		dt_converter = pd.to_datetime(_df['due_date'], format='%Y-%m-%d')
		if get_date == 'today':
			return dt_converter == _today
		if get_date == 'week':
			return dt_converter > _today
		if get_date == 'past':
			return dt_converter < _today
	else:
		return pd.Series()


def create_filter(request, _df: pd.DataFrame, column_name: str) -> pd.Series:
	"""создаем столбец data frame с перечнем фильтующих значений (bool) для дальнейшего использоваиня цепочки фильтров.
    """
	request_data = request.POST.getlist(column_name)

	if request_data:
		try:
			_df[column_name] = _df[column_name].apply(
				lambda x: getattr(x, 'name') if hasattr(x, 'name') else x
			)
			res = _df[column_name].isin(request_data)
			return res
		except Exception as e:
			print(e)
			return pd.Series()
	else:
		return _df[column_name].apply(lambda x: True)


def apply_filter(request, _df: pd.DataFrame, _filtered_value_list: list[str]) -> pd.Series:
	"""Назначаем фильтр data frame. Data filter назначаем отдельно."""

	intersection_list = list(set(request.POST).intersection(_filtered_value_list))
	try:
		dt_query = create_df_data_filter_choices(request, _df)
		if intersection_list:  # если есть фильтра кроме data filter
			query_list = [create_filter(request, _df, val) for val in intersection_list]
			if not dt_query.empty:
				return reduce(lambda x, y: x & y, query_list) & dt_query  # назначаем data filter
			else:
				return reduce(lambda x, y: x & y, query_list)
		if not dt_query.empty:  # если есть только data filter
			return dt_query
	except Exception as e:
		print(e)
		return pd.Series()


def create_pivot_table(model, qs, _replaced_list: list[str],
                       columns_name: str = 'contract',
                       index_name: list[str] = None,
                       filter_fields: str = None,
                       ) -> str:
	index_name = index_name if index_name else ['contractor']
	pivot_table = create_df_from_model(model, qs)
	pivot_table = pivot_table[pivot_table[filter_fields] > 0] if filter_fields else pivot_table
	for col_name in _replaced_list:
		pivot_table[col_name] = pivot_table[col_name].apply(
			lambda x: x.name if x else None
		)
	pivot_table = pivot_table.pivot_table(
		values='price',
		index=index_name,
		columns=[columns_name],
		aggfunc='sum',
		margins=True,
		margins_name="ИТОГО"
	)
	_renamed_dict = renamed_dict(model)
	pivot_table.index.name = _renamed_dict.get('contractor')
	pivot_table.columns.name = ""
	pivot_table = pivot_table.map(lambda x: humanize.intcomma(x).replace(',', ' '))
	pivot_table = pivot_table.to_html(classes="table table-striped table-bordered",
	                                  table_id='TaskTable',
	                                  index=True,
	                                  show_dimensions=False,
	                                  render_links=True,
	                                  justify='center',
	                                  escape=False,
	                                  na_rep='-',
	                                  )
	return pivot_table