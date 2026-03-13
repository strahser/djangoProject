import os
import re
import unicodedata

def sanitize_filename(filename: str, replacement: str = '_') -> str:
    """
    Очищает имя файла от недопустимых символов для Windows.
    Заменяет \ / : * ? " < > | и управляющие символы на replacement.
    Также ограничивает длину имени.
    """
    # Нормализация юникода
    filename = unicodedata.normalize('NFKD', filename)
    # Заменяем запрещённые символы
    invalid_chars = r'[\\/*?:"<>|\x00-\x1f]'
    filename = re.sub(invalid_chars, replacement, filename)
    # Убираем точки в начале и конце (проблемы с . и ..)
    filename = filename.strip('. ')
    # Ограничение длины (макс 255 для Windows, оставим запас)
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[:200 - len(ext)] + ext
    return filename

def clean(text):
    # clean text for creating a folder
    return "".join(c if c.isalnum() else "_" for c in text)