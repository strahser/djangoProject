# -*- coding: utf-8 -*-
"""Тесты автономного скрипта scripts/create_dated_folder.py.

Скрипт создаёт папку с датой в АКТИВНОЙ панели Total Commander через
внутренние команды TC (cm_MkDir / cm_RenameOnly, сообщение WM_USER+1075)
и включает режим переименования.

Проверяем:
  * чистые функции (имя папки, создание на диске, запасной путь);
  * что номера команд TC совпадают с локальным TOTALCMD.INC — иначе
    скрипт молча перестанет работать после обновления Total Commander;
  * что скрипт не падает без запущенного TC (создаёт папку напрямую).

Сам Total Commander в тестах не нужен: обращения к нему заглушены.
"""
import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / 'create_dated_folder.py'


def _load_script():
    spec = importlib.util.spec_from_file_location('create_dated_folder', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


try:
    cdf = _load_script()
    IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001 — скрипт использует Win32 API
    cdf = None
    IMPORT_ERROR = exc


@unittest.skipIf(cdf is None, f'скрипт не импортируется: {IMPORT_ERROR}')
class DatedFolderScriptTest(unittest.TestCase):
    """Чистая логика скрипта."""

    def test_dated_name_default_format(self):
        day = datetime(2026, 10, 21, 15, 30)
        self.assertEqual(cdf.dated_name(day), '2026_10_21_')

    def test_dated_name_with_suffix(self):
        day = datetime(2026, 10, 21)
        self.assertEqual(cdf.dated_name(day, 'КП'), '2026_10_21_КП')

    def test_dated_name_strips_extra_underscores(self):
        day = datetime(2026, 10, 21)
        self.assertEqual(cdf.dated_name(day, '_КП_'), '2026_10_21_КП')
        self.assertEqual(cdf.dated_name(day, '  '), '2026_10_21_')

    def test_create_folder_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            day = datetime(2026, 10, 21)
            folder = cdf.create_folder_on_disk(Path(tmp), suffix='КП', day=day)
            self.assertTrue(folder.is_dir())
            self.assertEqual(folder.name, '2026_10_21_КП')
            # повторный вызов не падает и не удаляет содержимое
            (folder / 'file.txt').write_text('x', encoding='utf-8')
            again = cdf.create_folder_on_disk(Path(tmp), suffix='КП', day=day)
            self.assertEqual(again, folder)
            self.assertTrue((folder / 'file.txt').exists())

    def test_main_falls_back_to_disk_without_total_commander(self):
        """Без запущенного TC скрипт создаёт папку напрямую и не падает."""
        with tempfile.TemporaryDirectory() as tmp:
            log_file = Path(tmp) / 'last_run.log'
            with mock.patch.object(cdf, 'LOG_FILE', log_file), \
                    mock.patch.object(cdf, 'find_tc_window', return_value=None), \
                    mock.patch.object(cdf, 'launch_total_commander',
                                      return_value=False):
                code = cdf.main(['--base', tmp, '--name', '2026_10_21_',
                                 '--no-pause'])
            self.assertEqual(code, 0)
            self.assertTrue((Path(tmp) / '2026_10_21_').is_dir())
            self.assertTrue(log_file.exists())

    def test_main_rejects_empty_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_file = Path(tmp) / 'last_run.log'
            with mock.patch.object(cdf, 'LOG_FILE', log_file):
                code = cdf.main(['--base', tmp, '--name', '   ', '--no-pause'])
            self.assertEqual(code, 2)

    def test_default_mode_only_inserts_name(self):
        """По умолчанию скрипт только вставляет дату в окно ввода TC."""
        with tempfile.TemporaryDirectory() as tmp:
            log_file = Path(tmp) / 'last_run.log'
            with mock.patch.object(cdf, 'LOG_FILE', log_file), \
                    mock.patch.object(cdf, 'find_tc_window', return_value=1234), \
                    mock.patch.object(cdf, '_window_title', return_value='TC'), \
                    mock.patch.object(cdf, 'open_name_input',
                                      return_value=(99, 100)) as insert, \
                    mock.patch.object(cdf, 'create_folder_in_tc') as create:
                code = cdf.main(['--name', '2026_10_21_', '--no-pause'])
            self.assertEqual(code, 0)
            insert.assert_called_once()
            self.assertEqual(insert.call_args.args[1], '2026_10_21_')
            create.assert_not_called()

    def test_auto_mode_creates_and_renames(self):
        """С --auto скрипт доводит всё сам: Enter + переименование."""
        with tempfile.TemporaryDirectory() as tmp:
            log_file = Path(tmp) / 'last_run.log'
            with mock.patch.object(cdf, 'LOG_FILE', log_file), \
                    mock.patch.object(cdf, 'find_tc_window', return_value=1234), \
                    mock.patch.object(cdf, '_window_title', return_value='TC'), \
                    mock.patch.object(cdf, 'open_name_input',
                                      return_value=(99, 100)) as insert, \
                    mock.patch.object(cdf, 'create_folder_in_tc',
                                      return_value=(True, '2026_10_21_',
                                                    True)) as create:
                code = cdf.main(['--auto', '--name', '2026_10_21_',
                                 '--no-pause'])
            self.assertEqual(code, 0)
            insert.assert_not_called()
            create.assert_called_once()
            self.assertTrue(create.call_args.kwargs['do_rename'])

    def test_total_cmd_inc_command_ids(self):
        """Номера команд TC должны совпадать с TOTALCMD.INC."""
        inc = None
        for candidate in (Path(r'C:\Program Files\totalcmd\TOTALCMD.INC'),
                          Path(r'C:\Program Files\Total Commander\TotalCMD.INC'),
                          Path(r'C:\Program Files (x86)\Total Commander\TotalCMD.INC')):
            if candidate.exists():
                inc = candidate
                break
        if inc is None:
            self.skipTest('TOTALCMD.INC не найден — нечего сверять')
        text = inc.read_text(encoding='utf-8', errors='replace')
        for name, expected in (('cm_MkDir', cdf.CM_MKDIR),
                               ('cm_RenameOnly', cdf.CM_RENAME_ONLY),
                               ('cm_CopySrcPathToClip', cdf.CM_COPY_SRC_PATH)):
            self.assertIn(f'{name}={expected};', text,
                          f'{name} в скрипте={expected}, а в {inc.name} — иное')

    def test_command_message_is_wm_user_1075(self):
        """Механизм отправки команд TC — сообщение 1075 (см. wiki TC)."""
        self.assertEqual(cdf.TC_MSG, 1075)
        self.assertEqual(cdf.TC_WINDOW_CLASS, 'TTOTAL_CMD')


if __name__ == '__main__':
    unittest.main()
