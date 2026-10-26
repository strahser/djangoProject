"""Фоновый прогон правил автоматизации (вынесено из views.py).

rule_run_now раньше вызывал engine.process_emails(Email.objects.all())
синхронно в HTTP-запросе: на реальном объёме базы (110+ МБ, тысячи писем)
правила с exists()-проверками дают сотни тысяч запросов — браузер
гарантированно упирался в таймаут. Теперь views зовут run_rule_async —
тот же движок в daemon-потоке (как push_seen_async, блок 30), запрос
возвращается сразу, результат пишется в EmailAutomationLog и в log-файл.
"""
from loguru import logger


def run_rule_over_all(rule) -> int:
    """Применить правило ко всем письмам. Возвращает число обработанных.

    Пишем результат в logger: пользователь увидит итог в Automation log
    (одна запись на срабатывание), а не в тосте — как и раньше.
    """
    from Emails.models import Email
    from .rule_engine import RuleEngine

    engine = RuleEngine()
    count = engine.process_emails(Email.objects.order_by('id').iterator())
    logger.info(
        f'Правило "{rule.name}" (id={rule.id}) применено в фоне '
        f'к {count} письмам')
    return count


def run_rule_async(rule):
    """Тот же прогон в daemon-потоке: запрос не ждёт обработку.

    Возвращает поток (тестам — join для детерминированности).
    """
    import threading
    thread = threading.Thread(
        target=_run_safe, args=(rule,),
        name='email-rules-run', daemon=True)
    thread.start()
    return thread


def _run_safe(rule):
    """Обёртка: падение правила не должно оставлять поток без следа."""
    try:
        run_rule_over_all(rule)
    except Exception as e:
        logger.exception(f'Фоновый прогон правила id={rule.id} упал: {e}')
