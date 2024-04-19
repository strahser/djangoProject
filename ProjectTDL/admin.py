from django.contrib import admin
from AdminUtils import duplicate_event, get_standard_display_list, get_filtered_registered_models
from ProjectTDL.forms import EmailForm, TaskAdminUpdate, TaskAdminUpdateDate
from ProjectTDL.models import *
from ProjectContract.models import *
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from import_export.fields import Field
from StaticData.models import DesignChapter
from admin_form_action import form_action


class DesignChapterResource(resources.ModelResource):
	class Meta:
		model = DesignChapter
		fields = ['id', 'name', 'short_name']


class TaskResource(resources.ModelResource):
	id = Field(attribute='id')
	project_site__name = Field(attribute='project_site__name')
	sub_project__name = Field(attribute='sub_project__name')
	building_number__name__name = Field(attribute='building_number__name__name')
	building_number__building_number = Field(attribute='building_number__building_number')
	design_chapter__short_name = Field(attribute='design_chapter__short_name')
	name = Field(attribute='name')
	description = Field(attribute='description')
	status__name = Field(attribute='status__name')
	due_date = Field(attribute='due_date')
	subtask_sum = Field(attribute='subtask_sum')

	class Meta:
		model = Task
		fields = ('id', 'project_site__name',
		          'sub_project__name',
		          'building_number__name__name',
		          'building_number__building_number', 'design_chapter__short_name', 'name', 'description',
		          'status__name', 'due_date'
		          )
		export_order = ('id', 'project_site__name')


class TaskInline(admin.TabularInline):
	model = SubTask
	extra = 0
	fields = get_standard_display_list(SubTask, additional_list=['creation_stamp'])
	readonly_fields = ('creation_stamp',)


class EmailInline(admin.TabularInline):
	model = Email
	extra = 0
	fields = ['project_site', 'contractor', 'email_type', 'name', 'parent']
	readonly_fields = ['create_admin_link']
	form = EmailForm


class ContractPaymentsInline(admin.TabularInline):
	model = ContractPayments
	extra = 0


excluding_list = [Task, Contract, DesignChapter, Email]


@admin.register(*get_filtered_registered_models('ProjectContract', excluding_list))
@admin.register(*get_filtered_registered_models('StaticData', excluding_list))
@admin.register(*get_filtered_registered_models('ProjectTDL', excluding_list))
class UniversalAdmin(admin.ModelAdmin):
	actions = [duplicate_event]
	list_display_links = ('id', 'name')
	list_per_page = 10

	def get_list_display(self, request):
		return get_standard_display_list(self.model, excluding_list=['creation_stamp', 'update_stamp', 'link', 'body'])


@admin.register(Task)
class TaskAdmin(ImportExportModelAdmin):
	actions = [duplicate_event, 'update_price', 'update_due_date']
	list_display_links = ('id','name',)
	list_display = get_standard_display_list(Task, additional_list=[],
	                                         excluding_list=['description', 'parent', 'owner',])
	list_editable = ('status',  'price', 'due_date',)#удалил 'category', 'contractor','contract',
	list_filter = ['project_site__name', 'sub_project', 'building_number', 'status', 'category', 'contractor','contract',]
	search_fields = ['name', 'project_site__name']
	inlines = [TaskInline, EmailInline]
	resource_classes = [TaskResource]
	list_per_page = 10
	actions_on_bottom = True

	@form_action(TaskAdminUpdateDate)
	@admin.action(description='Обновить дату')
	def update_due_date(self, request, queryset):
		_form = request.form
		for task in queryset:
			_form.update_due_date(task)

	@form_action(TaskAdminUpdate)
	@admin.action(description='Обновить Цену')
	def update_price(self, request, queryset):
		price_form = request.form
		for task in queryset:
			price_form.update_price(task)

	class Media(object):
		js = ('admin/js/admin.js',)
		# css = {"all": ("admin/admin_css.css",)}


@admin.register(Contract)
class ContractAdmin(UniversalAdmin):
	actions = [duplicate_event]
	inlines = (ContractPaymentsInline,)


@admin.register(DesignChapter)
class ContractAdmin(ImportExportModelAdmin):
	actions = [duplicate_event]
	resource_classes = [DesignChapterResource]
	list_display = get_standard_display_list(DesignChapter)


@admin.register(Email)
class EmailAdmin(ImportExportModelAdmin):
	list_display = get_standard_display_list(Email, excluding_list=['body', 'subject', 'link'],
	                                         additional_list=['create_admin_link'])

	list_filter = ['project_site', 'contractor', 'sender']
	list_display_links = ['name']
