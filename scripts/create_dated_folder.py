# -*- coding: utf-8 -*-
r"""Создать в АКТИВНОЙ панели Total Commander папку с датой и включить режим переименования.

Автономный скрипт (только стандартная библиотека) — запускается прямо
с рабочего ПК, без Django и без сервера.

КАК РАБОТАЕТ (внутренние команды Total Commander, без эмуляции клавиш)
--------------------------------------------------------------------
TC умеет принимать внутренние команды сообщением WM_USER+1075 (1075)
в окно класса TTOTAL_CMD — это штатный механизм, описанный на wiki TC
(«AutoHotkey: Send a command to Total Commander») и используемый
сторонними утилитами (SendTCCommand).

ЧТО ДЕЛАЕТ
-----------
По умолчанию (быстрый режим): скрипт открывает окно ввода имени новой
папки в АКТИВНОЙ панели TC (как F7) и вписывает в него дату — всё.
Дальше вы сами: Enter — создать папку, Shift+F6 — переименовать.

С флагом --auto скрипт доводит всё сам:
    Enter          → папка создана и выделена
    cm_RenameOnly  (1002) → открывается «Переименовать» (как Shift+F6) —
                            это edit-контрол TInEdit прямо в панели
    EM_SETSEL      → снимаем выделение, каретка в конце имени:
                            сразу дописывайте суффикс

Скорость: в быстром режиме дата вставлена за ~0.1–0.2 с, в автоматическом
папка готова к правке имени за ~0.2–0.5 с. Фиксированных пауз нет: скрипт
ждёт конкретных событий (появилось окно ввода, в фокусе поле TInEdit) и
опрашивает их каждые 20–60 мс. Если TC ещё не обновил панель после
создания папки, команда переименования повторяется (она безопасна — имя
не меняется).

Почему не TOTALCMD.EXE /O: ключ /O открывает путь в ДРУГОЙ панели TC
(не в активной) — скрипт «проваливался» не туда.
Почему не SendInput с F7: клавиши уходят в окно, которое сейчас на
переднем плане, и при запуске кнопкой из TC это работает ненадёжно.

Запуск:
    .venv\Scripts\python.exe scripts\create_dated_folder.py
    .venv\Scripts\python.exe scripts\create_dated_folder.py --auto
    .venv\Scripts\python.exe scripts\create_dated_folder.py --suffix "КП"
    .venv\Scripts\python.exe scripts\create_dated_folder.py --name "2026_10_21_КП"

КНОПКА В ПАНЕЛИ TOTAL COMMANDER (штатный способ, без консоли):
    Правый клик по панели кнопок → «Изменить…» (Change) → «Добавить» (Add):
      Команда:       "D:\Автоматизация\djangoProject\.venv\Scripts\pythonw.exe"
      Параметры:     "D:\Автоматизация\djangoProject\scripts\create_dated_folder.py" --no-pause
      Рабочая папка: D:\Автоматизация\djangoProject\scripts
      Подсказка:     Создать папку по дате
      Иконка:        любая (например, из wcmicons.dll)
    pythonw.exe — запуск БЕЗ окна консоли (главное «неудобство» снято).
    Всё, что происходит, пишется в scripts\last_run.log.
"""
from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

#: Куда писать лог (рядом со скриптом).
LOG_FILE = Path(__file__).resolve().parent / 'last_run.log'

#: Явные пути к Total Commander (если нестандартная установка).
TOTALCMD_PATHS = [
    Path(r'C:\Program Files\totalcmd\TOTALCMD.EXE'),
    Path(r'C:\Program Files\Total Commander\Totalcmd.exe'),
    Path(r'C:\Program Files (x86)\Total Commander\Totalcmd.exe'),
    Path(r'C:\Total Commander\Totalcmd.exe'),
    Path(r'C:\Tools\Total Commander\Totalcmd.exe'),
]

# ---------------------------------------------------------------------------
# Константы Total Commander
# ---------------------------------------------------------------------------
TC_MSG = 1075                  # WM_USER+1075 — отправка внутренней команды TC
CM_MKDIR = 907                 # «Создать каталог» (F7) — в активной панели
CM_RENAME_ONLY = 1002          # «Переименовать» (Shift+F6)
CM_COPY_SRC_PATH = 2029        # «Копировать путь исходной панели в буфер»

TC_WINDOW_CLASS = 'TTOTAL_CMD'       # главное окно TC
TC_COMBO_CLASS = 'TCOMBOINPUT'      # поле ввода TC (создание папки)
TC_INEDIT_CLASS = 'TInEdit'          # поле переименования прямо в панели

WM_GETTEXT = 0x000D
WM_SETTEXT = 0x000C
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
EM_SETSEL = 0x00B1
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


# ---------------------------------------------------------------------------
# логирование
# ---------------------------------------------------------------------------
def log(message: str) -> None:
    """Запись в лог рядом со скриптом (pythonw не показывает консоль)."""
    try:
        stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with LOG_FILE.open('a', encoding='utf-8') as fh:
            fh.write(f'{stamp}  {message}\n')
    except OSError:
        pass
    try:
        print(message)
    except (OSError, ValueError):
        pass


def dated_name(day: datetime | None = None, suffix: str = '') -> str:
    """Имя папки: 2026_10_21_ + суффикс (хвост подчёркивания оставлен
    намеренно, чтобы дописать суффикс вручную и переименовать)."""
    day = day or datetime.now()
    base = day.strftime('%Y_%m_%d_')
    suffix = (suffix or '').strip().strip('_').strip()
    return base + suffix if suffix else base


# ---------------------------------------------------------------------------
# Win32
# ---------------------------------------------------------------------------
user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = wintypes.LPARAM
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HANDLE
kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
kernel32.GlobalUnlock.restype = wintypes.BOOL


def _class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _window_title(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def _pid_of(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _enum_windows() -> list[tuple[int, str, int, bool]]:
    """Все верхнеуровневые окна: (hwnd, класс, pid, видимое)."""
    out: list[tuple[int, str, int, bool]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lparam):
        out.append((hwnd, _class_name(hwnd), _pid_of(hwnd),
                    bool(user32.IsWindowVisible(hwnd))))
        return True

    user32.EnumWindows(cb, 0)
    return out


def _enum_children(parent: int) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lparam):
        out.append((hwnd, _class_name(hwnd)))
        return True

    user32.EnumChildWindows(parent, cb, 0)
    return out


def find_tc_window() -> int | None:
    """HWND главного окна Total Commander (приоритет — окно на переднем плане)."""
    windows = [w for w in _enum_windows() if w[1] == TC_WINDOW_CLASS]
    if not windows:
        return None
    foreground = user32.GetForegroundWindow()
    for hwnd, _cls, _pid, _vis in windows:
        if hwnd == foreground:
            return hwnd
    visible = [w for w in windows if w[3]]
    return (visible[0] if visible else windows[0])[0]


def windows_of_class(prefix: str) -> set[int]:
    """HWND всех окон, класс которых начинается с prefix."""
    return {hwnd for hwnd, cls, _pid, _vis in _enum_windows()
            if cls.startswith(prefix)}


def find_new_window(prefix: str, before: set[int],
                    timeout: float = 5.0,
                    interval: float = 0.02) -> int | None:
    """Дождаться НОВОГО окна с заданным классом (например TCOMBOINPUT)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for hwnd, cls, _pid, _vis in _enum_windows():
            if cls.startswith(prefix) and hwnd not in before:
                return hwnd
        time.sleep(interval)
    return None


class _GUIINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('flags', wintypes.DWORD),
                ('hwndActive', wintypes.HWND), ('hwndFocus', wintypes.HWND),
                ('hwndCapture', wintypes.HWND), ('hwndMenuOwner', wintypes.HWND),
                ('hwndMoveSize', wintypes.HWND), ('hwndCaret', wintypes.HWND),
                ('rcCaret', wintypes.RECT)]


user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                             ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.c_void_p]
user32.GetGUIThreadInfo.restype = wintypes.BOOL


def focused_editor(tc_hwnd: int) -> int | None:
    """HWND поля переименования TC (TInEdit), если оно сейчас в фокусе.

    TC 11 открывает переименование прямо в панели: это обычный edit-контрол
    класса TInEdit, который получает фокус. Он и служит признаком того,
    что режим переименования включён.
    """
    thread_id = user32.GetWindowThreadProcessId(tc_hwnd, None)
    info = _GUIINFO()
    info.cbSize = ctypes.sizeof(_GUIINFO)
    if user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
        focus = info.hwndFocus
        if focus and _class_name(focus) == TC_INEDIT_CLASS:
            return focus
    return None


def caret_to_end(hwnd: int) -> None:
    """Снять выделение и поставить каретку в конец текста (EM_SETSEL)."""
    length = len(get_text(hwnd))
    user32.SendMessageW(hwnd, EM_SETSEL, length, length)


def find_edit(parent: int) -> int | None:
    """Поле ввода внутри окна TC."""
    for hwnd, cls in _enum_children(parent):
        if cls.lower() in ('edit', 'tedit'):
            return hwnd
    return None


def set_text(hwnd: int, text: str) -> None:
    buf = ctypes.create_unicode_buffer(text)
    user32.SendMessageW(hwnd, WM_SETTEXT, 0,
                        ctypes.cast(buf, ctypes.c_void_p).value)


def get_text(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(1024)
    user32.SendMessageW(hwnd, WM_GETTEXT, 1024,
                        ctypes.cast(buf, ctypes.c_void_p).value)
    return buf.value


def press_enter(hwnd: int) -> None:
    user32.PostMessageW(hwnd, WM_KEYDOWN, VK_RETURN, 0)
    user32.PostMessageW(hwnd, WM_KEYUP, VK_RETURN, 0)


def tc_command(hwnd: int, command: int, wait: bool = False) -> None:
    """Внутренняя команда TC (1075).

    wait=False → PostMessage: команда, открывающая модальный диалог
    (cm_MkDir, cm_RenameOnly), иначе SendMessage блокирует вызывающий
    процесс до закрытия диалога (дедлок).
    """
    if wait:
        user32.SendMessageW(hwnd, TC_MSG, command, 0)
    else:
        user32.PostMessageW(hwnd, TC_MSG, command, 0)


# ---------------------------------------------------------------------------
# буфер обмена (нужен только для диагностики — путь активной панели)
# ---------------------------------------------------------------------------
def clipboard_get_text() -> str | None:
    for _ in range(5):
        if user32.OpenClipboard(None):
            try:
                handle = user32.GetClipboardData(CF_UNICODETEXT)
                if not handle:
                    return None
                ptr = kernel32.GlobalLock(handle)
                if not ptr:
                    return None
                text = ctypes.c_wchar_p(ptr).value
                kernel32.GlobalUnlock(handle)
                return text
            finally:
                user32.CloseClipboard()
        time.sleep(0.2)
    return None


def clipboard_set_text(text: str) -> bool:
    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        data = ctypes.create_unicode_buffer(text)
        size = ctypes.sizeof(data)
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not handle:
            return False
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return False
        ctypes.memmove(ptr, data, size)
        kernel32.GlobalUnlock(handle)
        user32.SetClipboardData(CF_UNICODETEXT, handle)
        return True
    finally:
        user32.CloseClipboard()


def active_panel_path(tc_hwnd: int) -> str | None:
    """Путь АКТИВНОЙ панели TC (команда cm_CopySrcPathToClip).

    Команда портит буфер обмена — прежнее содержимое сохраняем и
    восстанавливаем.
    """
    saved = clipboard_get_text()
    tc_command(tc_hwnd, CM_COPY_SRC_PATH, wait=True)
    time.sleep(0.3)
    path = clipboard_get_text()
    if saved is not None and path is not None and saved != path:
        clipboard_set_text(saved)
    return path


# ---------------------------------------------------------------------------
# основной сценарий
# ---------------------------------------------------------------------------
def cancel_rename(tc_hwnd: int, editor: int) -> None:
    """Отменить открытое переименование (ESC), ничего не переименовав."""
    for hwnd in (editor, tc_hwnd):
        user32.PostMessageW(hwnd, WM_KEYDOWN, VK_ESCAPE, 0)
        user32.PostMessageW(hwnd, WM_KEYUP, VK_ESCAPE, 0)
    time.sleep(0.1)


def wait_rename_editor(tc_hwnd: int, name: str, timeout: float = 4.0,
                       interval: float = 0.06) -> tuple[int | None, bool]:
    """Дождаться поля переименования (TInEdit) и проверить, что оно открыто
    именно для нужной папки.

    Возвращает (hwnd редактора, совпало ли имя). Если редактор открылся на
    другом файле — он отменяется (ESC), чтобы ничего не переименовать.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        editor = focused_editor(tc_hwnd)
        if editor is None:
            if user32.GetForegroundWindow() != tc_hwnd:
                # TC не на переднем плане — переименование не откроется.
                return None, False
            # TC мог ещё не обновить панель после создания папки —
            # повторяем команду (она безопасна: имя не меняется).
            tc_command(tc_hwnd, CM_RENAME_ONLY)
            time.sleep(interval)
            continue
        shown = get_text(editor)
        if not shown or shown == name:
            return editor, shown == name
        # открыто не то — отменяем
        cancel_rename(tc_hwnd, editor)
        time.sleep(interval)
    return None, False


def open_name_input(tc_hwnd: int, name: str) -> tuple[int | None, int | None]:
    """Открыть окно ввода имени новой папки (как F7) и вписать в него имя.

    Окно остаётся открытым — пользователь жмёт Enter (создать папку) и,
    при желании, Shift+F6 (переименовать).
    Возвращает (HWND окна ввода, HWND поля ввода).
    """
    log('cm_MkDir (907) — окно ввода имени новой папки')
    before_combo = windows_of_class(TC_COMBO_CLASS)
    tc_command(tc_hwnd, CM_MKDIR)
    combo = find_new_window(TC_COMBO_CLASS, before_combo, timeout=6.0)
    if not combo:
        log('Окно ввода TC не появилось (cm_MkDir не сработал).')
        return None, None
    edit = find_edit(combo)
    if not edit:
        log('В окне TC не найдено поле ввода.')
        return combo, None
    set_text(edit, name)
    return combo, edit


def create_folder_in_tc(tc_hwnd: int, name: str,
                        do_rename: bool = True) -> tuple[bool, str | None, bool]:
    """Полный автомат: создать папку и открыть режим переименования.

    Возвращает (успех, имя, открыт ли редактор).
    """
    started = time.time()

    combo, edit = open_name_input(tc_hwnd, name)
    if edit is None:
        return False, None, False
    time.sleep(0.03)
    press_enter(edit)

    # ждём, пока TC закроет окно ввода и создаст папку
    deadline = time.time() + 5.0
    while time.time() < deadline and user32.IsWindowVisible(combo):
        time.sleep(0.02)

    if not do_rename:
        log(f'Папка «{name}» создана в активной панели '
            f'({time.time() - started:.2f} с).')
        return True, name, False

    log('cm_RenameOnly (1002) — режим переименования (Shift+F6)')
    editor, matched = wait_rename_editor(tc_hwnd, name)
    if editor:
        caret_to_end(editor)
        log(f'Папка «{name}» создана, режим переименования открыт, '
            f'каретка в конце имени ({time.time() - started:.2f} с).')
        return True, name, True
    if matched:
        log('Папка создана, но редактор не подтверждён.')
        return True, name, False
    log('Папка создана, но окно переименования не открылось '
        '(TC не на переднем плане?).')
    return True, name, False


def create_folder_on_disk(base: Path, suffix: str = '',
                          day: datetime | None = None) -> Path:
    """Запасной вариант: создать папку напрямую на диске (без TC)."""
    base.mkdir(parents=True, exist_ok=True)
    folder = base / dated_name(day, suffix)
    if not folder.exists():
        folder.mkdir()
    return folder


def find_total_commander() -> str | None:
    """Путь к Totalcmd.exe: явные пути → реестр → типовые места."""
    env_tc = os.environ.get('TOTALCMD')
    if env_tc and Path(env_tc).exists():
        return env_tc
    for candidate in TOTALCMD_PATHS:
        if candidate.exists():
            return str(candidate)
    try:
        import winreg
    except ImportError:  # pragma: no cover — только Windows
        return None
    for hive, sub in (
            (winreg.HKEY_LOCAL_MACHINE,
             r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Totalcmd.exe'),
            (winreg.HKEY_CURRENT_USER,
             r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Totalcmd.exe')):
        try:
            with winreg.OpenKey(hive, sub) as key:
                path, _ = winreg.QueryValueEx(key, None)
                if path and Path(path).exists():
                    return path
        except OSError:
            pass
    for env in ('ProgramFiles', 'ProgramFiles(x86)', 'ProgramW6432'):
        base = os.environ.get(env)
        if base:
            candidate = Path(base) / 'totalcmd' / 'TOTALCMD.EXE'
            if candidate.exists():
                return str(candidate)
    return None


def launch_total_commander(folder: Path | None = None) -> bool:
    """Запустить TC (если ещё не запущен)."""
    tc = find_total_commander()
    if not tc:
        log(f'Total Commander не найден. Проверенные пути: '
            f'{[str(p) for p in TOTALCMD_PATHS]}')
        return False
    cmd = [tc]
    if folder:
        cmd.append(str(folder))
    try:
        subprocess.Popen(cmd)
        return True
    except OSError as exc:
        log(f'Не удалось запустить TC ({tc}): {exc}')
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Создать в активной панели Total Commander папку с датой '
                    'и включить режим переименования '
                    '(cm_MkDir / Enter / cm_RenameOnly).')
    parser.add_argument('base_pos', nargs='?', default=None, metavar='base',
                        help='запасной путь, если TC недоступен')
    parser.add_argument('--base', dest='base_opt', default=None,
                        help='то же, что позиционный base (запасной вариант)')
    parser.add_argument('--name', default=None,
                        help='имя папки (по умолчанию — дата: 2026_10_21_)')
    parser.add_argument('--suffix', default='',
                        help='суффикс имени: --suffix "КП" → 2026_10_21_КП')
    parser.add_argument('--auto', action='store_true',
                        help='сразу создать папку и открыть режим '
                             'переименования (по умолчанию скрипт только '
                             'вставляет дату в окно ввода и выходит — '
                             'Enter и Shift+F6 нажимаете вы)')
    parser.add_argument('--no-rename', action='store_true',
                        help='(с --auto) не открывать режим переименования')
    parser.add_argument('--no-pause', action='store_true',
                        help='не ждать Enter в конце')
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse печатает usage в stderr — при запуске через pythonw.exe
        # консоли нет, и ошибка исчезала бесследно. Пишем в лог.
        log(f'Ошибка аргументов (код {exc.code}). Справка: --help')
        raise

    name = (args.name or dated_name(suffix=args.suffix)).strip()
    if not name:
        log('Пустое имя папки.')
        return 2

    tc_hwnd = find_tc_window()
    if tc_hwnd:
        log(f'Окно TC: {_window_title(tc_hwnd)!r} (hwnd=0x{tc_hwnd:X})')
    else:
        log('Total Commander не запущен — пробую запустить.')
        if launch_total_commander():
            time.sleep(2.5)
            tc_hwnd = find_tc_window()

    if tc_hwnd:
        if args.auto:
            ok, _name, renamed = create_folder_in_tc(
                tc_hwnd, name, do_rename=not args.no_rename)
            if not ok:
                log('Не удалось создать папку через TC.')
                log(f'Активная панель: {active_panel_path(tc_hwnd)}')
                return 3
            if not renamed and not args.no_rename:
                log('Подсказка: нажмите Shift+F6 вручную — откроется '
                    'переименование только что созданной папки.')
        else:
            _combo, edit = open_name_input(tc_hwnd, name)
            if edit is None:
                log('Не удалось открыть окно ввода имени в TC.')
                log(f'Активная панель: {active_panel_path(tc_hwnd)}')
                return 3
            log(f'Дата «{name}» вставлена в окно ввода TC. '
                'Enter — создать папку, Shift+F6 — переименовать.')
    else:
        base = Path(args.base_opt or args.base_pos or
                    Path(__file__).resolve().parent.parent)
        # Имя должно совпадать с тем, что скрипт вставил бы в TC: раньше
        # запасной путь игнорировал --name и создавал папку с текущей датой.
        folder = base / name
        folder.mkdir(parents=True, exist_ok=True)
        log(f'TC недоступен — папка создана напрямую: {folder} '
            '(режим переименования недоступен).')

    if not args.no_pause and sys.stdin is not None and sys.stdin.isatty():
        try:
            input('Enter — выход...')
        except (EOFError, KeyboardInterrupt):
            pass
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — скрипт запускается без консоли
        # Падать молча нельзя: при запуске через pythonw.exe пользователь
        # не увидит ни ошибки, ни результата. Пишем в лог.
        log(f'ОШИБКА: {exc!r}')
        raise SystemExit(1)
