from urllib.parse import urlparse
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect, HttpResponse
from django.urls import reverse_lazy
from django.views.generic import UpdateView, DeleteView
from django.contrib import messages
from ProjectTDL.Tables import TaskTable, create_filter_qs, data_filter_qs, StaticFilterSettings
from ProjectTDL.forms import EmailForm, TaskFilterForm, TaskUpdateForm, TaskAdminUpdateDate, TaskAdminUpdate, \
	TaskUpdateValuesForm
from ProjectTDL.models import Task, SubTask
from ProjectTDL.querys.EmailCreate import parsing_form_for_e_mail_path, process_e_mail, add_form_data_to_data_base, \
	make_folder

from services.DataFrameRender.RenderDfFromModel import renamed_dict, CloneRecord, create_df_from_model, ButtonData, \
	create_group_button, HTML_DF_PROPERTY
from django_tables2 import RequestConfig, TemplateColumn


def task_action(request):
	if request.method == "POST":
		pks = request.POST.getlist("selection")
		if pks: request.session['pks'] = pks
		_form = TaskUpdateValuesForm(request.POST or None)
		if request.session.get('pks', None):
			all_fields = [f.name for f in Task._meta.fields]
			update_dict = {}
			for k, v in _form.data.items():
				if k in all_fields and v:
					update_dict[k] = v
			if update_dict:
				try:
					selected_objects = Task.objects.filter(pk__in=request.session.get('pks'))
					selected_objects.update(**update_dict)
					request.session['pks'] = None
					for data in selected_objects:
						messages.success(request, data)
					return redirect('home')
				except Exception as e:
					messages.error(request, e)
					return redirect('home')
			else:
				_form = TaskUpdateValuesForm()
				return render(request, 'ProjectTDL/Universal_update_form.html', {'form': _form})
		else:
			messages.error(request, 'Не выбраны данные')
			return redirect('home')
	else:
		messages.error(request, 'Не выбраны данные')
		return redirect('home')


def index(request):
	qs = create_filter_qs(request, StaticFilterSettings.filtered_value_list).filter(
		**data_filter_qs(request, 'due_date'))
	table = None
	_pivot_ui = None
	pivot_table_list = []
	gant_table = ''
	if request.method == 'POST':
		_form = TaskFilterForm(request.POST)  # fiter
		if 'submit' in request.POST and _form.is_valid():
			table = TaskTable(qs)
			RequestConfig(request).configure(table)
			for name, _column in zip(StaticFilterSettings.pivot_columns_names,
			                         StaticFilterSettings.pivot_columns_values):
				pivot_table1 = {"name": name,
				                'table': Task.create_pivot_table(qs, StaticFilterSettings.replaced_list, _column)}
				pivot_table_list.append(pivot_table1)
		# df = create_df_from_model(Task, qs)
		# _pivot_ui = pivot_ui(df, rows=['contractor'], cols=['category'],
		#                      outfile_path="templates/ProjectTDL/pivottablejs.html")
		if 'save_attachments' in request.POST and _form.is_valid():
			return TaskTable.Save_table_django(Task, qs, excluding_list=StaticFilterSettings.export_excluding_list)
	else:
		_form = TaskFilterForm()
		table = TaskTable(qs)
	context = {'form': _form, 'table': table, "gant_table": gant_table, 'pivot_table_list': pivot_table_list,
	           'tasks': qs}
	return render(request, 'ProjectTDL/index.html', context)


def TaskCloneView(request, pk):
	queryset = Task.objects.filter(pk=pk)
	CloneRecord(queryset)
	messages.success(request, f'Запись {queryset.first().name} была скопирована ')
	return redirect("home")


def SubTaskCloneView(request, pk):
	queryset = SubTask.objects.filter(pk=pk)
	CloneRecord(queryset)
	messages.success(request, f'Запись {queryset.first().name} была скопирована ')
	previous_url = request.META.get('HTTP_REFERER')
	if previous_url and urlparse(previous_url).hostname == request.get_host():
		return HttpResponseRedirect(previous_url)


class TaskDeleteView(DeleteView):
	model = Task
	template_name = 'ProjectTDL/Delete_Form.html'

	def get_context_data(self, **kwargs):
		context = super(DeleteView, self).get_context_data(**kwargs)
		context['Name'] = "Обновление полей модели "
		if '__next__' in self.request.POST:
			context['i__next__'] = self.request.POST['__next__']
		else:
			context['i__next__'] = self.request.META['HTTP_REFERER']
		return context

	def get_success_url(self):
		self.url = self.request.POST['__next__']
		return self.url


class TaskUpdateView(UpdateView):
	model = Task
	form_class = TaskUpdateForm
	template_name = 'ProjectTDL/Update_form.html'
	success_url = reverse_lazy('home')

	def get_context_data(self, **kwargs):
		c_object = self.get_object()
		context = super(TaskUpdateView, self).get_context_data(**kwargs)
		qs = SubTask.objects.filter(parent__id=c_object.id)
		if qs:
			df_initial = create_df_from_model(SubTask, qs)
			button_data_copy = ButtonData('SubTaskCloneView', "pk", name='📄')
			button_data_delete = ButtonData('SubTaskDeleteView', "pk", cls='danger', name='X')
			button_data_update = ButtonData('SubTaskUpdateView', "pk")
			# переопределяем название задачи - добавляем ссылку на update
			df_initial['name'] = df_initial.apply(lambda x: button_data_update.create_text_link(x['id'], x['name']),
			                                      axis=1)
			button_copy = df_initial.apply(lambda x: button_data_copy.button_link(x['id']), axis=1)
			button_delete = df_initial.apply(lambda x: button_data_delete.button_link(x['id']), axis=1)
			df_initial['действия'] = create_group_button([button_copy, button_delete])
			data = df_initial.rename(renamed_dict(SubTask), axis='columns').to_html(**HTML_DF_PROPERTY)
			context['data'] = data
		return context


class SubTaskUpdateView(UpdateView):
	model = SubTask
	template_name = 'ProjectTDL/Universal_update_form.html'
	fields = '__all__'

	def get_context_data(self, **kwargs):
		context = super(UpdateView, self).get_context_data(**kwargs)
		context['Name'] = "Обновление полей модели "
		if '__next__' in self.request.POST:
			context['i__next__'] = self.request.POST['__next__']
		else:
			context['i__next__'] = self.request.META['HTTP_REFERER']
		return context

	def get_success_url(self):
		self.url = self.request.POST['__next__']
		return self.url


class SubTaskDeleteView(TaskDeleteView):
	model = SubTask
	template_name = 'ProjectTDL/Delete_Form.html'


def e_mail_add(request):
	if request.method == 'POST':
		_form = EmailForm(request.POST)
		if 'create_folder' in request.POST and _form.is_valid():
			parsing_form_for_e_mail_path(_form)
			make_folder(_form.cleaned_data['link'])
			return render(request, 'ProjectTDL/e_mail_form.html',
			              {'form': _form, 'data_path': _form.cleaned_data['link']})

		if 'save_attachments' in request.POST and _form.is_valid():
			_parsed_form = parsing_form_for_e_mail_path(_form)
			make_folder(_form.cleaned_data['link'])
			parsing_form_data = process_e_mail(_parsed_form, request)
			add_form_data_to_data_base(parsing_form_data, request)
			return render(request, 'ProjectTDL/e_mail_form.html',
			              {'form': _form, 'data_path': _form.cleaned_data['link']})
	else:
		_form = EmailForm()
		return render(request, 'ProjectTDL/e_mail_form.html', {'form': _form, 'data_path': None})
