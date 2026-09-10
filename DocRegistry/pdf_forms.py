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
        Paragraph(f'<b>Здание:</b> {entry.building.name if entry and entry.building else "—"}', s['n']),
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
        Paragraph(f'<b>Здание:</b> {entry.building.name if entry.building else "—"}', s['n']),
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


CUSTOMER = 'ООО «ТиЭйч-РУС Милк Фуд»'
OBJECT = ('«Комплекс молочного животноводства на 6000 фуражных коров», расположенный по адресу: '
          'Московская область, Волоколамский район, территория ФГОУ СПО Волоколамский аграрный техникум “Холмогорка”')
DESIGNER_DEFAULT = 'ИП РОДИН'


def approval_sheet_bytes(iss, signers, month_ru: str | None = None) -> bytes:
    """Лист согласования в производство работ — повторяет бумажный образец
    (Подано\\2026\\...\\Лист согласования.docx): шапка + §1 подписанты + §2 перечень + примечание."""
    from datetime import date as _date

    entry = iss.entry
    when = iss.waybill_date or _date.today()
    designer = entry.developer.name if entry.developer else DESIGNER_DEFAULT
    revs = list(entry.revisions.order_by('rev_no')) if entry else []
    rows = []
    if not revs:
        rows.append((entry.cipher or '',
                     entry.building.name if entry.building else '',
                     f'{when.year} г.'))
    for r in revs:
        fname = r.attachment.filename if r.attachment else (r.file.name.split('/')[-1] if r.file else '')
        rows.append((entry.cipher or '',
                     fname[:80] or (entry.building.name if entry.building else ''),
                     f'{when.year} г.'))
    header = _project_header([entry.project] if entry.project else [], designer)
    return _approval_sheet(when, month_ru, signers, rows, entry.cipher or '', header)


def approval_sheet_multi(entries, signers, when=None, month_ru: str | None = None) -> bytes:
    """Лист согласования сразу на несколько записей реестра (§2 — по строке на запись).

    Для админ-экшена: выделил записи → бланк PDF. Шапка — из проекта записей;
    несколько проектов — таблицей. Подписанты — единый список.
    """
    from datetime import date as _date

    when = when or _date.today()
    designers = {(e.developer.name if e.developer else '') for e in entries}
    designers.discard('')
    designer = next(iter(designers)) if len(designers) == 1 else DESIGNER_DEFAULT
    rows = []
    for e in entries:
        name = e.building.name if e.building else ''
        if e.file_name and e.file_name != e.cipher:
            name = f'{name} — {e.file_name[:60]}' if name else e.file_name[:80]
        ver = e.submit_date.strftime('%d.%m.%Y') if e.submit_date else f'{when.year} г.'
        rows.append((e.cipher or '', name, ver))
    ciphers = [e.cipher or '' for e in entries]
    # «общий том» — только когда у ВСЕХ строк один непустой шифр; иначе примечание не нужно
    note_tom = ciphers[0] if ciphers and all(c and c == ciphers[0] for c in ciphers) else ''
    seen, projects = set(), []
    for e in entries:
        if e.project and e.project_id not in seen:
            seen.add(e.project_id)
            projects.append(e.project)
    header = _project_header(projects, designer)
    return _approval_sheet(when, month_ru, signers, rows, note_tom, header)


def _project_header(projects, designer_fallback: str = '') -> list:
    """Шапка листа: один проект — строки заказчик/объект/проектировщик,
    несколько — таблица (Проект | Заказчик | Объект | Проектировщик), иначе константы."""
    s = _styles()
    if len(projects) == 1:
        p = projects[0]
        designer = p.designer or designer_fallback or DESIGNER_DEFAULT
        return [
            Paragraph(f'<b>Заказчик:</b> {p.customer or CUSTOMER}'
                      f'<br/><b>Объект:</b> {p.object_full or OBJECT}', s['n']),
            Paragraph(f'<b>Проектировщик:</b> {designer}', s['n']),
        ]
    if len(projects) > 1:
        data = [[Paragraph('<b>Проект</b>', s['cellc']), Paragraph('<b>Заказчик</b>', s['cellc']),
                 Paragraph('<b>Объект</b>', s['cellc']), Paragraph('<b>Проектировщик</b>', s['cellc'])]]
        for p in projects:
            data.append([Paragraph(f'{p.code} — {p.name}', s['cell']),
                         Paragraph(p.customer or CUSTOMER, s['cell']),
                         Paragraph(p.object_full or OBJECT, s['cell']),
                         Paragraph(p.designer or designer_fallback or DESIGNER_DEFAULT, s['cell'])])
        t = Table(data, colWidths=[28 * mm, 45 * mm, 65 * mm, 34 * mm])
        t.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, (0, 0, 0)),
                               ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                               ('TOPPADDING', (0, 0), (-1, -1), 6),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 10)]))
        return [t]
    return [
        Paragraph(f'<b>Заказчик:</b> {CUSTOMER}<br/><b>Объект:</b> {OBJECT}', s['n']),
        Paragraph(f'<b>Проектировщик:</b> {designer_fallback or DESIGNER_DEFAULT}', s['n']),
    ]


def _approval_sheet(when, month_ru, signers, rows, note_tom, header) -> bytes:
    """Ядро листа: шапка + §1 подписанты + §2 перечень (rows: cipher, name, version) + примечание."""
    from django.utils import timezone

    s = _styles()
    buf, doc = _doc()
    stamped_at = timezone.localtime(timezone.now()).strftime('%d.%m.%Y %H:%M')
    months = {'01': 'января', '02': 'февраля', '03': 'марта', '04': 'апреля',
              '05': 'мая', '06': 'июня', '07': 'июля', '08': 'августа',
              '09': 'сентября', '10': 'октября', '11': 'ноября', '12': 'декабря'}
    date_ru = month_ru or f"{when.day} {months[when.strftime('%m')]} {when.year} г."
    story = [
        Paragraph('ЛИСТ СОГЛАСОВАНИЯ ПРОЕКТНОЙ/РАБОЧЕЙ ДОКУМЕНТАЦИИ', s['h']),
        Paragraph('В ПРОИЗВОДСТВО РАБОТ', s['h']),
        Spacer(1, 3 * mm),
        *header,
        Paragraph(f'<b>Дата:</b> {date_ru}', s['n']),
        Spacer(1, 3 * mm),
        Paragraph('<b>1. Подписи согласующих лиц</b>', s['nb']),
        Spacer(1, 2 * mm),
    ]
    head = [Paragraph('<b>Должность</b>', s['cellc']), Paragraph('<b>Подпись</b>', s['cellc']),
            Paragraph('<b>Расшифровка подписи</b>', s['cellc']), Paragraph('<b>Дата</b>', s['cellc'])]
    data = [head]
    for sg in signers:
        pos = sg.position.strip()
        if sg.company:
            pos += f' ({sg.company})'
        if sg.stamp:
            # штамп как э-подпись: СОГЛАСОВАНО + ФИО + дата/время генерации
            sign_cell = (f'<b><font color="#1a56db">СОГЛАСОВАНО</font></b><br/>'
                         f'{sg.person}<br/>{stamped_at}')
        else:
            sign_cell = ''
        data.append([Paragraph(pos, s['cell']), Paragraph(sign_cell, s['cell']),
                     Paragraph(sg.person or '', s['cell']), Paragraph(sg.mark or '', s['cell'])])
    t = Table(data, colWidths=[70 * mm, 30 * mm, 40 * mm, 32 * mm])
    t.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, (0, 0, 0)),
                           ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                           ('TOPPADDING', (0, 0), (-1, -1), 6),
                           ('BOTTOMPADDING', (0, 0), (-1, -1), 14)]))
    story += [t, Spacer(1, 4 * mm),
              Paragraph('<b>2. Перечень разделов, представленных на согласование</b>', s['nb']),
              Spacer(1, 2 * mm)]
    docs = [[Paragraph('<b>№ п/п</b>', s['cellc']), Paragraph('<b>Обозначение документа</b>', s['cellc']),
             Paragraph('<b>Наименование (кратко)</b>', s['cellc']),
             Paragraph('<b>Версия / дата изменения</b>', s['cellc'])]]
    for i, (cipher, name, ver) in enumerate(rows, start=1):
        docs.append([Paragraph(str(i), s['cellc']), Paragraph(cipher, s['cell']),
                     Paragraph(name, s['cell']), Paragraph(ver, s['cellc'])])
    t2 = Table(docs, colWidths=[14 * mm, 58 * mm, 66 * mm, 34 * mm])
    t2.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, (0, 0, 0)),
                            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                            ('TOPPADDING', (0, 0), (-1, -1), 6),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 12)]))
    story += [t2, Spacer(1, 4 * mm),
              Paragraph('<b>Примечание:</b>', s['nb'])]
    if note_tom:
        story.append(Paragraph(f'Все перечисленные разделы входят в общий том {note_tom}.', s['n']))
    story += [Paragraph('Подписи проставляются после фактического согласования документации.', s['n']),
              Paragraph('Лист согласования является неотъемлемой частью комплекта рабочей документации.', s['n'])]
    doc.build(story)
    return buf.getvalue()
