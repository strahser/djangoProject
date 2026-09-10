"""Печатные формы РД: лист согласования + накладная в ПР (M1 DOC-4, канон §6).

Образцы в УтвПРРАБ — сканы без текстового слоя, поэтому генерируем свои PDF
(reportlab, шрифт Arial для кириллицы). Структура повторяет бумажные образцы.
"""
from __future__ import annotations

import io
from datetime import date

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    _HAS_RL = True
except ImportError:
    _HAS_RL = False


def _need_rl():
    if not _HAS_RL:
        raise RuntimeError(
            'Нет reportlab: E:\\Venvs\\djangoProject\\Scripts\\python -m pip install reportlab')


def _styles():
    _need_rl()
    try:
        pdfmetrics.registerFont(TTFont('Arial', r'C:\Windows\Fonts\arial.ttf'))
        pdfmetrics.registerFont(TTFont('Arial-Bold', r'C:\Windows\Fonts\arialbd.ttf'))
        font, font_b = 'Arial', 'Arial-Bold'
    except Exception:
        font, font_b = 'Helvetica', 'Helvetica-Bold'
    return {
        'h': ParagraphStyle('h', fontName=font_b, fontSize=14, leading=17, alignment=1, spaceAfter=6 * mm),
        'n': ParagraphStyle('n', fontName=font, fontSize=10, leading=13),
        'nb': ParagraphStyle('nb', fontName=font_b, fontSize=10, leading=13),
        'cell': ParagraphStyle('cell', fontName=font, fontSize=9, leading=11),
        'cellc': ParagraphStyle('cellc', fontName=font, fontSize=9, leading=11, alignment=1),
    }


def _doc():
    _need_rl()
    buf = io.BytesIO()
    return buf, SimpleDocTemplate(buf, pagesize=A4,
                                  leftMargin=18 * mm, rightMargin=15 * mm,
                                  topMargin=15 * mm, bottomMargin=15 * mm)


def _sign_table(s, rows: int = 4) -> Table:
    data = [[Paragraph('<b>№</b>', s['cellc']), Paragraph('<b>Замечание / решение</b>', s['cellc']),
             Paragraph('<b>Подпись, дата</b>', s['cellc'])]]
    for i in range(1, rows + 1):
        data.append([Paragraph(str(i), s['cellc']), Paragraph('', s['cell']),
                     Paragraph('', s['cell'])])
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
    s = _styles()
    rev = rm.revision
    entry = rev.entry
    buf, doc = _doc()
    today = date.today().strftime('%d.%m.%Y')
    story = [
        Paragraph('ЛИСТ СОГЛАСОВАНИЯ', s['h']),
        Paragraph('рабочей документации (замечания)', s['n']),
        Spacer(1, 4 * mm),
        Paragraph(f'<b>Шифр:</b> {entry.cipher if entry else "—"} &nbsp;&nbsp; '
                  f'<b>Код реестра:</b> {entry.code if entry else "—"} &nbsp;&nbsp; '
                  f'<b>Ревизия:</b> {rev.rev_no}', s['n']),
        Paragraph(f'<b>Файл:</b> {rev.attachment.filename if rev.attachment else (rev.file.name if rev.file else "—")}', s['n']),
        Paragraph(f'<b>Здание:</b> {entry.building_name if entry else "—"}', s['n']),
        Paragraph(f'<b>Дата:</b> {today}', s['n']),
        Spacer(1, 3 * mm),
        Paragraph('<b>Замечание:</b>', s['nb']),
        Paragraph((rm.text or '').replace('\n', '<br/>'), s['n']),
        Spacer(1, 4 * mm),
        _sign_table(s),
        Spacer(1, 6 * mm),
        Paragraph('Согласовано _________________ / _________________ / «___» __________ 20___ г.', s['n']),
    ]
    doc.build(story)
    return buf.getvalue()


def waybill_bytes(iss) -> bytes:
    """Накладная на передачу РД в производство работ по DocIssue."""
    s = _styles()
    entry = iss.entry
    buf, doc = _doc()
    story = [
        Paragraph(f'НАКЛАДНАЯ № {iss.waybill_no}', s['h']),
        Paragraph('на передачу рабочей документации в производство работ', s['n']),
        Spacer(1, 4 * mm),
        Paragraph(f'<b>Дата:</b> {iss.waybill_date.strftime("%d.%m.%Y") if iss.waybill_date else "___"}', s['n']),
        Paragraph(f'<b>Шифр:</b> {entry.cipher} &nbsp;&nbsp; <b>Код реестра:</b> {entry.code}', s['n']),
        Paragraph(f'<b>Здание:</b> {entry.building_name or "—"}', s['n']),
        Paragraph(f'<b>Файл:</b> {entry.file_name or "—"}', s['n']),
        Paragraph(f'<b>Папка выдачи (сеть):</b> {iss.network_path or "___"}', s['n']),
        Spacer(1, 4 * mm),
    ]
    data = [[Paragraph('<b>№</b>', s['cellc']), Paragraph('<b>Документ</b>', s['cellc']),
             Paragraph('<b>Кол. экз.</b>', s['cellc']), Paragraph('<b>Примечание</b>', s['cellc'])],
            [Paragraph('1', s['cellc']), Paragraph(f'{entry.cipher}', s['cell']),
             Paragraph('', s['cellc']), Paragraph('', s['cell'])]]
    t = Table(data, colWidths=[12 * mm, 100 * mm, 25 * mm, 35 * mm])
    t.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, (0, 0, 0)),
                           ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                           ('TOPPADDING', (0, 0), (-1, -1), 6),
                           ('BOTTOMPADDING', (0, 0), (-1, -1), 14)]))
    story += [t, Spacer(1, 6 * mm),
              Paragraph('Передал _________________ / _________________ / «___» __________ 20___ г.', s['n']),
              Spacer(1, 3 * mm),
              Paragraph('Принял _________________ / _________________ / «___» __________ 20___ г.', s['n'])]
    doc.build(story)
    return buf.getvalue()
