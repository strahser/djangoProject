"""Печатные формы РД: лист согласования + накладная в ПР (M1 DOC-4, канон §6).

Образцы в УтвПРРАБ — сканы без текстового слоя, поэтому генерируем свои PDF
(reportlab, шрифт Arial для кириллицы). Структура повторяет бумажные образцы.
"""
from __future__ import annotations

import io
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle

try:
    pdfmetrics.registerFont(TTFont('Arial', r'C:\Windows\Fonts\arial.ttf'))
    pdfmetrics.registerFont(TTFont('Arial-Bold', r'C:\Windows\Fonts\arialbd.ttf'))
    FONT, FONT_B = 'Arial', 'Arial-Bold'
except Exception:
    FONT, FONT_B = 'Helvetica', 'Helvetica-Bold'

_H = ParagraphStyle('h', fontName=FONT_B, fontSize=14, leading=17, alignment=1, spaceAfter=6 * mm)
_N = ParagraphStyle('n', fontName=FONT, fontSize=10, leading=13)
_NB = ParagraphStyle('nb', fontName=FONT_B, fontSize=10, leading=13)
_CELL = ParagraphStyle('cell', fontName=FONT, fontSize=9, leading=11)
_CELLC = ParagraphStyle('cellc', parent=_CELL, alignment=1)


def _doc():
    buf = io.BytesIO()
    return buf, SimpleDocTemplate(buf, pagesize=A4,
                                  leftMargin=18 * mm, rightMargin=15 * mm,
                                  topMargin=15 * mm, bottomMargin=15 * mm)


def _sign_table(rows: int = 4) -> Table:
    data = [[Paragraph('<b>№</b>', _CELLC), Paragraph('<b>Замечание / решение</b>', _CELLC),
             Paragraph('<b>Подпись, дата</b>', _CELLC)]]
    for i in range(1, rows + 1):
        data.append([Paragraph(str(i), _CELLC), Paragraph('', _CELL),
                     Paragraph('', _CELL)])
    t = Table(data, colWidths=[12 * mm, 105 * mm, 55 * mm])
    t.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, (0, 0, 0)),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [(1, 1, 1), (0.96, 0.96, 0.96)]),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
    ]))
    return t


def remark_sheet_bytes(rm) -> bytes:
    """Лист согласования по DocRemark."""
    rev = rm.revision
    entry = rev.entry
    buf, doc = _doc()
    today = date.today().strftime('%d.%m.%Y')
    story = [
        Paragraph('ЛИСТ СОГЛАСОВАНИЯ', _H),
        Paragraph('рабочей документации (замечания)', _N),
        Spacer(1, 4 * mm),
        Paragraph(f'<b>Шифр:</b> {entry.cipher if entry else "—"} &nbsp;&nbsp; '
                  f'<b>Код реестра:</b> {entry.code if entry else "—"} &nbsp;&nbsp; '
                  f'<b>Ревизия:</b> {rev.rev_no}', _N),
        Paragraph(f'<b>Файл:</b> {rev.attachment.filename if rev.attachment else (rev.file.name if rev.file else "—")}', _N),
        Paragraph(f'<b>Здание:</b> {entry.building_name if entry else "—"}', _N),
        Paragraph(f'<b>Дата:</b> {today}', _N),
        Spacer(1, 3 * mm),
        Paragraph('<b>Замечание:</b>', _NB),
        Paragraph((rm.text or '').replace('\n', '<br/>'), _N),
        Spacer(1, 4 * mm),
        _sign_table(),
        Spacer(1, 6 * mm),
        Paragraph('Согласовано _________________ / _________________ / «___» __________ 20___ г.', _N),
    ]
    doc.build(story)
    return buf.getvalue()


def waybill_bytes(iss) -> bytes:
    """Накладная на передачу РД в производство работ по DocIssue."""
    entry = iss.entry
    buf, doc = _doc()
    story = [
        Paragraph(f'НАКЛАДНАЯ № {iss.waybill_no}', _H),
        Paragraph('на передачу рабочей документации в производство работ', _N),
        Spacer(1, 4 * mm),
        Paragraph(f'<b>Дата:</b> {iss.waybill_date.strftime("%d.%m.%Y") if iss.waybill_date else "___"}', _N),
        Paragraph(f'<b>Шифр:</b> {entry.cipher} &nbsp;&nbsp; <b>Код реестра:</b> {entry.code}', _N),
        Paragraph(f'<b>Здание:</b> {entry.building_name or "—"}', _N),
        Paragraph(f'<b>Файл:</b> {entry.file_name or "—"}', _N),
        Paragraph(f'<b>Папка выдачи (сеть):</b> {iss.network_path or "___"}', _N),
        Spacer(1, 4 * mm),
    ]
    data = [[Paragraph('<b>№</b>', _CELLC), Paragraph('<b>Документ</b>', _CELLC),
             Paragraph('<b>Кол. экз.</b>', _CELLC), Paragraph('<b>Примечание</b>', _CELLC)],
            [Paragraph('1', _CELLC), Paragraph(f'{entry.cipher}', _CELL),
             Paragraph('', _CELLC), Paragraph('', _CELL)]]
    t = Table(data, colWidths=[12 * mm, 100 * mm, 25 * mm, 35 * mm])
    t.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, (0, 0, 0)),
                           ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                           ('TOPPADDING', (0, 0), (-1, -1), 6),
                           ('BOTTOMPADDING', (0, 0), (-1, -1), 14)]))
    story += [t, Spacer(1, 6 * mm),
              Paragraph('Передал _________________ / _________________ / «___» __________ 20___ г.', _N),
              Spacer(1, 3 * mm),
              Paragraph('Принял _________________ / _________________ / «___» __________ 20___ г.', _N)]
    doc.build(story)
    return buf.getvalue()
