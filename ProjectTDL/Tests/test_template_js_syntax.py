# -*- coding: utf-8 -*-
"""Синтаксис inline-JS тяжёлых шаблонов (esprima).

Прецедент: болтающийся блок + лишняя } в custom_task_view_enhanced.html
молча роняли ВЕСЬ custom-js (дерево, фильтры, DnD) — Django рендерит
страницу 200, а браузер молча не выполняет скрипт. Тест ловит это на CI.
Ограничение: сырой исходник шаблона (с Django-тегами) должен оставаться
валидным JS — {% url %}/{% static %} внутри строковых литералов этому
удовлетворяют; {% if %}-логику внутрь JS не тащить.
"""
import re

from django.test import TestCase


def _inline_scripts(template_name):
    from django.template.loader import get_template
    src = get_template(template_name).template.source
    return re.findall(r'<script(?![^>]*src=)[^>]*>(.*?)</script>', src, re.S)


class InlineJsSyntaxTest(TestCase):
    def test_task_view_js_parses(self):
        esprima = __import__('esprima')
        blocks = _inline_scripts('ProjectTDL/custom_task_view_enhanced.html')
        self.assertTrue(blocks, 'inline-скрипт не найден')
        for i, js in enumerate(blocks):
            with self.subTest(block=i):
                try:
                    esprima.parseScript(js, {'tolerant': False})
                except esprima.Error as e:
                    self.fail(f'JS syntax error в блоке {i}: {e}')
