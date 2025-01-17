from django.contrib import admin

from AdminUtils import get_filtered_registered_models, get_standard_display_list


@admin.register(*get_filtered_registered_models('PersonalData'))
class UniversalAdmin(admin.ModelAdmin):
	list_display_links = ('id', 'name')
	list_per_page = 20

	def get_list_display(self, request):
		return get_standard_display_list(self.model, excluding_list=['creation_stamp', 'update_stamp', 'link', 'body'])
