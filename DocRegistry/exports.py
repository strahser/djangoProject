# -*- coding: utf-8 -*-
"""Выгрузка реестра РД (М1/К1) в Excel с оформлением.

Колонки — как в исходнике accdb [01 Реестр]: код, здание, раздел,
№ здания, файл, разраб., дата подачи. Красивая шапка: титул + жирная
шапка с заливкой, зебра, границы, автофильтр, заморозка, ширины.
"""
from io import BytesIO

HEADERS = ['Код', 'Проект', 'Наименование здания', 'Раздел', 'Номер здания',
           'Имя эл. файла', 'Разраб.', 'Дата подачи']
WIDTHS = [8, 12, 40, 12, 14, 70, 24, 14]


def build_registry_xlsx(entries, project_code: str) -> bytes:
    """Собрать xlsx реестра. entries — итерируемые записи с select_related.
    Возвращает байты файла."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = Workbook()
    ws = wb.active
    ws.title = f'Реестр {project_code}'
    ncols = len(HEADERS)

    title_fill = PatternFill('solid', fgColor='1F3864')
    head_fill = PatternFill('solid', fgColor='2E75B6')
    zebra_fill = PatternFill('solid', fgColor='DDEBF7')
    white_font = Font(bold=True, color='FFFFFF', size=11)
    title_font = Font(bold=True, color='FFFFFF', size=14)
    thin = Side(style='thin', color='B0B0B0')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    left_wrap = Alignment(horizontal='left', vertical='center', wrap_text=True)

    # Титул
    from django.utils import timezone
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    title_cell = ws.cell(row=1, column=1,
                         value=f"Реестр РД — {project_code} "
                               f"({timezone.now():%d.%m.%Y})")
    title_cell.font = title_font
    title_cell.fill = title_fill
    title_cell.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[1].height = 26

    # Шапка
    for i, h in enumerate(HEADERS, start=1):
        cell = ws.cell(row=2, column=i, value=h)
        cell.font = white_font
        cell.fill = head_fill
        cell.alignment = center
        cell.border = border
    ws.row_dimensions[2].height = 30

    # Данные
    for r, e in enumerate(entries, start=3):
        b = e.building
        bn = e.building_no
        values = [
            e.code,
            e.project_site.name if e.project_site else '',
            b.name if b else '',
            e.section.short if e.section else '',
            bn.number if bn else '',
            e.file_name or '',
            e.developer.name if e.developer else '',
            e.submit_date if e.submit_date else '',
        ]
        for i, v in enumerate(values, start=1):
            cell = ws.cell(row=r, column=i, value=v)
            cell.border = border
            cell.alignment = left_wrap if i == 6 else center
            if r % 2 == 0:
                cell.fill = zebra_fill
        if e.submit_date:
            ws.cell(row=r, column=8).number_format = 'DD.MM.YYYY'

    from openpyxl.utils import get_column_letter
    for i, w in enumerate(WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.auto_filter.ref = f'A2:{get_column_letter(len(HEADERS))}{ws.max_row}'
    ws.freeze_panes = 'A3'

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
