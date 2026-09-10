"""Подсказки маппинга [02 Задачи] accdb -> TaskNode (канон §4 п.2, DOC-5).

Read-only: ничего не пишет, только печатает топ-3 кандидата на задачу
(пересечение токенов Задача+чертеж vs name+description). Привязку делает
человек проставлением DocRevision.task / accdb_task_code.
"""
from __future__ import annotations

import re

from django.core.management.base import BaseCommand

from DocRegistry import accdb as live

STOP = {'для', 'как', 'при', 'или', 'это', 'все', 'всю', 'там', 'уже', 'если',
        'про', 'без', 'над', 'под', 'что', 'как', 'and', 'the'}


def tokens(text: str) -> set[str]:
    words = re.findall(r'[а-яёa-z0-9]+', (text or '').lower())
    return {w for w in words if len(w) >= 4 and w not in STOP}


def match_score(accdb_text: str, node_text: str) -> float:
    """Доля токенов accdb-задачи, найденных в карточке TaskNode (0..1)."""
    a, b = tokens(accdb_text), tokens(node_text)
    if not a:
        return 0.0
    return len(a & b) / len(a)


class Command(BaseCommand):
    help = 'Подсказки маппинга [02 Задачи] -> TaskNode (read-only)'

    def add_arguments(self, parser):
        parser.add_argument('--min-score', type=float, default=0.3)
        parser.add_argument('--limit', type=int, default=0, help='0 = все 92')

    def handle(self, *args, **options):
        from ProjectTDL.models import TaskNode

        tasks = live.read_tasks()
        nodes = list(TaskNode.objects.all())
        self.stdout.write(f'accdb задач: {len(tasks)}, TaskNode: {len(nodes)}')
        shown = 0
        for t in tasks:
            if options['limit'] and shown >= options['limit']:
                break
            acc = f"{t.get('Задача', '')} {t.get('чертеж', '')}"
            scored = sorted(
                ((match_score(acc, f'{n.name} {n.description or ""}'), n) for n in nodes),
                key=lambda x: -x[0])[:3]
            best = scored[0][0] if scored else 0.0
            if best < options['min_score']:
                self.stdout.write(
                    f"[{t.get('Код задачи', '?')}] {t.get('Задача', '')[:70]} -> НЕТ КАНДИДАТА (best {best:.2f})")
            else:
                cands = '; '.join(f'#{n.pk} {n.name[:50]} ({s:.2f})' for s, n in scored)
                self.stdout.write(f"[{t.get('Код задачи', '?')}] {t.get('Задача', '')[:70]} -> {cands}")
            shown += 1
