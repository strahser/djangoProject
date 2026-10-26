# -*- coding: utf-8 -*-
"""Пути почтового архива: единая точка разрешения устаревших корней.

В БД хранятся абсолютные пути (``Email.link``, ``Attachment.file_path``).
Исторически корень был ``e:\\...``, сейчас архив лежит на ``d:\\...``
(новые письма пишутся в ``E_MAIL_DIRECTORY`` из ``.env``). Чтобы переезд
диска не требовал правки тысяч строк, при чтении путь пропускается через
``resolve_email_path``:

1. существующий путь возвращается как есть;
2. если путь не найден, пробуется тот же относительный путь на текущем
   диске (``E_MAIL_DIRECTORY``) — это покрывает переименование диска
   ``e:`` → ``d:`` для любых подкаталогов, включая ``2024-06-26_архив``
   и ``M1``;
3. затем путь перебазируется по хвосту от каталога архива
   (``imap_attachments`` / ``sent`` / ``drafts``) на текущий корень или
   его родителя — на случай, если переехал не диск, а каталог.

Новые пути сохраняются от ``E_MAIL_DIRECTORY`` — код сохранения менять
не нужно. Для разовой чистки БД есть команда ``rewrite_email_paths``.
"""
import os

from django.conf import settings

#: Каталоги верхнего уровня внутри корня архива. По ним вычисляется «хвост»
#: пути, не зависящий от диска и имени корневой папки.
ARCHIVE_MARKERS = ('imap_attachments', 'sent', 'drafts')


def archive_root() -> str:
    """Текущий корень архива (``E_MAIL_DIRECTORY``)."""
    return str(getattr(settings, 'E_MAIL_DIRECTORY', '') or '')


def _normalize(path) -> str:
    return str(path or '').replace('/', '\\')


def _exists(path) -> bool:
    try:
        return bool(path) and os.path.exists(path)
    except (OSError, ValueError):
        return False


def replace_drive(path, drive):
    """Заменить букву диска в абсолютном пути (``e:\\...`` → ``d:\\...``).

    Возвращает ``None``, если путь не абсолютный или диск задан неверно.
    """
    normalized = _normalize(path)
    drive = _normalize(drive)
    if len(drive) != 2 or drive[1] != ':':
        return None
    if len(normalized) < 2 or normalized[1] != ':':
        return None
    return drive + normalized[2:]


def split_archive_tail(path):
    """Вернуть хвост пути от первого каталога архива (или ``None``).

    ``e:\\...\\Bitrix 24\\imap_attachments\\INBOX\\1\\file.pdf`` →
    ``imap_attachments\\INBOX\\1\\file.pdf``.
    """
    if not path:
        return None
    parts = [p for p in _normalize(path).split('\\') if p]
    lowered = [p.lower() for p in parts]
    indexes = [lowered.index(marker) for marker in ARCHIVE_MARKERS
               if marker in lowered]
    if not indexes:
        return None
    return '\\'.join(parts[min(indexes):])


def _candidate_roots():
    """Корни, под которыми может лежать архив.

    Текущий ``E_MAIL_DIRECTORY`` — новые письма (``...\\Bitrix 24``).
    Его родитель — старый архив (``...\\Переписка\\imap_attachments``).
    """
    root = archive_root()
    if not root:
        return []
    roots = [root]
    parent = os.path.dirname(root.rstrip('\\/'))
    if parent and os.path.normcase(parent) != os.path.normcase(root):
        roots.append(parent)
    return roots


def resolve_email_path(path):
    """Разрешить сохранённый путь с учётом текущего расположения архива.

    Существующий путь возвращается как есть (обычный случай). Для
    устаревшего пути сначала пробуется та же структура на текущем диске,
    затем — хвост от маркера архива под текущим корнем или его родителем.
    Пути вне архива (временные, тестовые) не трогаются.
    """
    if not path:
        return path
    if _exists(path):
        return path

    root = archive_root()
    if root:
        same_layout = replace_drive(path, root[:2])
        if same_layout and _exists(same_layout):
            return same_layout

    tail = split_archive_tail(path)
    if tail:
        for candidate_root in _candidate_roots():
            candidate = os.path.join(candidate_root, tail)
            if _exists(candidate):
                return candidate
        if root:
            # Файла пока нет — показываем наиболее вероятный путь.
            return os.path.join(root, tail)

    return path
