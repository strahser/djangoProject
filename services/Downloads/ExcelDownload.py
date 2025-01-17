import io
import pandas as pd


def to_list(element) -> list:
	if hasattr(element, "__iter__"):
		res = element
	else:
		res = [element]
	return res


def result_to_excel_add_table(df_dict: dict[str, pd.DataFrame],
                              excel_book_path: str,
                              index: bool = False,
                              convert_to_table: bool = True,
                              renamed_sheet_dict: dict[str, str] = None,
                              condition_format_data=None
                              ):
	"""
    create new file excel. convert_to_table == True -> make smart excel table.
    df_dict {sheet_name:df}
    excel_book_path path to excel
    """

	def create_condition_format(ConditionFormatData, worksheet, max_row, max_col, pass_format):
		# https://fooobar.com/questions/16142772/painting-a-cell-in-excel-with-condition-using-python
		# https://xlsxwriter.readthedocs.io/worksheet.html#conditional_format%23conditional_format
		# https://stackoverflow.com/questions/44150078/python-using-pandas-to-format-excel-cell
		# Add a format for pass. Green fill with dark green text.
		pass_format = workbook.add_format({'bg_color': 'red', 'font_color': '#006100'})
		if ConditionFormatData:
			worksheet.conditional_format(0, 0, max_row, max_col, {'type': 'cell',
			                                                      'criteria': '>=',
			                                                      'value': 50,
			                                                      'format': pass_format}
			                             )
		worksheet.set_column(0, max_col - 1, 25)
		return worksheet

	def add_column_format():
		format_obj = workbook.add_format({'text_wrap': True})
		worksheet.set_column(4, 4, 60, format_obj)
		worksheet.set_column(3, 3, 30, format_obj)
		worksheet.set_column(8, 8, 15)
		worksheet.set_column(9, 9, 15)
		worksheet.set_landscape()
		worksheet.set_paper(9)
		worksheet.set_margins(left=1, right=0.5, top=0.5, bottom=0.5)
		return worksheet

	writer = pd.ExcelWriter(excel_book_path, engine='xlsxwriter')
	for sh_name in df_dict.keys():
		if convert_to_table:
			df_dict[sh_name].to_excel(
				writer,
				sheet_name=sh_name,
				startrow=0, startcol=0,
				header=True,
				index=index,
				freeze_panes=(1, 1),
				float_format="%.2f")
			workbook = writer.book
			worksheet = writer.sheets[sh_name]
			column_settings = [{'header': column}  for column in df_dict[sh_name]]
			# Применяем форматирование ко всем ячейкам
			(max_row, max_col) = df_dict[sh_name].shape
			worksheet.add_table(0, 0, max_row, max_col - 1,
			                    {'columns': column_settings,
			                     'banded_columns': True,
			                     'name': sh_name,
			                     'style': 'Table Style Light 8'})
			add_column_format()
			if renamed_sheet_dict:
				try:
					renamed_sheet = renamed_sheet_dict[sh_name]
					worksheet.set_header(f'&C&"Courier New,Bold Italic"{renamed_sheet}')
				except:
					worksheet.set_header(f'&C&"Courier New,Bold Italic"{sh_name}')
			else:
				worksheet.set_header(f'&C&"Courier New,Bold Italic"{sh_name}')
			worksheet.set_footer('&CPage &P of &N')
			worksheet.repeat_rows(0)
		else:
			df_dict[sh_name].to_excel(writer, sheet_name=sh_name,
			                          startrow=0, startcol=0, header=True, index=index, freeze_panes=(1, 1))
			workbook = writer.book
			worksheet = writer.sheets[sh_name]
	writer.close()


def df_to_excel_in_memory(df_list: list[pd.DataFrame], sheet_list: list[str],
                          index: bool = False,
                          convert_to_table: bool = True,
                          renamed_sheet_dict: dict[str, str] = None
                          ):
	df_list = to_list(df_list)
	sheet_list = to_list(sheet_list)
	df_sheet_dict = dict(zip(sheet_list, df_list))
	buffer = io.BytesIO()
	result_to_excel_add_table(df_sheet_dict,
	                          buffer,
	                          index=index,
	                          convert_to_table=convert_to_table,
	                          renamed_sheet_dict=renamed_sheet_dict
	                          )
	# writer.save()
	return buffer
