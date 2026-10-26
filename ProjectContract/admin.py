import sys

from django.contrib import admin, messages

from django.forms import Textarea
from ProjectContract.models import ContractPayments, Contractor, ContractChangeLog, ContractReminder, TaskComment, Tag, TaggedItem, Attachment, CashflowEntry, PaymentTaskLink, ContractEstimate, EstimateConcept, ContractStageLog, Act, EstimateTaskLink
from AdminUtils import get_standard_display_list, duplicate_event, duplicate_object
from ProjectContract.PivotTableUtility import create_calendar_list_view, create_payment_calendar
from ProjectContract.services import log_change

from ProjectContract.form import ContractPaymentsAdminForm
from django.db import models
from django.db.models import Sum, Value, DecimalField
from django.db.models.functions import Coalesce

from StaticData.models import ProjectSite
from .models import Contract  # Замените на свою модель
from loguru import logger
from django.utils.html import format_html
from urllib.parse import urlencode
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse, path
logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")


from .admin_filters import (
    ConceptActFilter, ConceptContractFilter, ConceptContractorFilter,
    ConceptEstimateFilter, ContractFilter, ContractorFilter,
    EstimateContractFilter, EstimateContractorFilter, PaymentTypeFilter,
    ProjectSiteFilter, _extract_scale,
)


class BaseAdmin(admin.ModelAdmin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app_name = self.model._meta.app_label
        self.model_name = self.model._meta.model_name

    def actions_column(self, obj):
        return format_html(
            '<a class="button" href="{}" title="Дублировать">{}</a>',
            reverse(f'admin:duplicate-{self.model_name}', args=[obj.pk]),
            '📋'  # Unicode символ для копирования
        )
    actions_column.short_description = format_html(
         '{}', '☰'
        )

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
             path(
                 f'duplicate-{self.model_name}/<int:pk>/',
                self.duplicate_view,
                 name=f'duplicate-{self.model_name}'
             ),
        ]
        return my_urls + urls

    def duplicate_view(self, request, pk):
        obj = self.get_object(request, pk)
        duplicate_object(obj)
        return redirect(request.META.get('HTTP_REFERER', reverse(f'admin:{self.app_name}_{self.model_name}_changelist')))


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0
    readonly_fields = ('file', 'uploaded_by', 'creation_stamp')
    fields = ('file', 'description', 'uploaded_by', 'creation_stamp')


class ContractPaymentsInline(admin.TabularInline):
    model = ContractPayments
    extra = 0
    readonly_fields = ( 'edit_link','duplicate_button')
    fields = ('name', 'payment_type', 'price','percent','made_payment', 'edit_link','duplicate_button')

    def duplicate_button(self, obj):
         if obj and obj.pk: # Проверка что обьект существует и есть pk.
            return format_html(
                '<a href="{}" title="Дублировать">&#128203;</a>',
                reverse('duplicate-contractpayment', args=[obj.pk])
            )
         else:
             return ""
    duplicate_button.short_description = "Дублировать"


    def add_payment_button(self, obj):
        contract_id = obj.pk if obj else None
        add_url = reverse('admin:ProjectContract_contractpayments_add')
        add_url = f"{add_url}?{urlencode({'contract': contract_id, '_next': reverse('admin:ProjectContract_contract_change', args=[contract_id])})}"
        return format_html(
            '<div style="margin-bottom: 10px;"><a class="button" href="{}">Добавить платеж</a></div>',
            add_url
        )
    def edit_link(self, obj):
        if obj and obj.pk:
            contract_id = obj.contract_id
            base_url = reverse('admin:ProjectContract_contractpayments_change', args=[obj.pk])
            edit_url = f"{base_url}?{urlencode({'_next': reverse('admin:ProjectContract_contract_change', args=[contract_id])})}"
            return format_html(
                '<a href="{}" class="button">✏️</a>',
                edit_url
            )
        return format_html(
            '<span style="color: gray;">Нет платежа</span>'
        )

    edit_link.short_description = "☰"


@admin.register(Contract)
class ContractAdmin(BaseAdmin):
    app_name = "ProjectContract"
    excluding_list = ['start_date', 'due_date', 'duration', 'proposal_link']
    additional_list =['paid_amount','unpaid_amount','status_check','actions_column']
    list_display = get_standard_display_list(Contract, excluding_list=excluding_list,additional_list=additional_list)
    list_filter = get_standard_display_list(Contract, excluding_list=['id', 'proposal_number', 'price', 'name'])
    actions = [duplicate_event]
    inlines = (ContractPaymentsInline, AttachmentInline)
    change_list_template = 'jazzmin/admin/change_list_contract.html'

    def changelist_view(self, request, extra_context=None):
        # Один рендер: пивоты/итоги докладываем в context_data уже отрендеренного
        # (но ещё не сериализованного) TemplateResponse. Ф2: считать ДДС из БД.
        extra_context = extra_context or {}
        _, original_get = _extract_scale(request)
        try:
            response = super().changelist_view(request, extra_context=extra_context)
        finally:
            request.GET = original_get
        if hasattr(response, "context_data"):
            before = set(extra_context)
            tables = create_calendar_list_view(request, response, extra_context)
            if isinstance(tables, dict):
                response.context_data.update(
                    {k: v for k, v in tables.items() if k not in before})
            try:
                qs = response.context_data["cl"].queryset
                # Два запроса вместо трёх. ВАЖНО: нельзя мешать Sum('price')
                # с Sum по contractpayments в одном aggregate — JOIN
                # размножит строки договора (цена посчитается N раз).
                total_price = qs.aggregate(total=Sum('price'))['total']
                paid_unpaid = qs.aggregate(
                    paid=Coalesce(Sum('contractpayments__price', filter=models.Q(
                        contractpayments__made_payment=True)), Value(0),
                        output_field=DecimalField(max_digits=12, decimal_places=2)),
                    unpaid=Coalesce(Sum('contractpayments__price', filter=models.Q(
                        contractpayments__made_payment=False)), Value(0),
                        output_field=DecimalField(max_digits=12, decimal_places=2)),
                )
                total_paid = paid_unpaid['paid'] or 0
                total_unpaid = paid_unpaid['unpaid'] or 0
                response.context_data.update({
                    'total_price': total_price,
                    'total_paid': total_paid,
                    'total_unpaid': total_unpaid,
                    'total_status': (total_price or 0) - (total_paid + total_unpaid),
                })
            except KeyError:
                pass
        return response

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        log_change(contract=obj, action='updated' if change else 'created',
                   details=str(obj), user=request.user)

    def delete_model(self, request, obj):
        log_change(contract=obj, action='deleted',
                   details=f'{obj} (id={obj.pk}, цена={obj.price})',
                   user=request.user)
        super().delete_model(request, obj)

    def get_queryset(self, request):
        # Суммы по платежам одним запросом вместо 4 aggregates на строку
        # (paid + unpaid + status_check дергает оба ещё раз).
        # Плюс FK changelist-колонок одним JOIN вместо 3 запросов на строку.
        qs = super().get_queryset(request)
        return qs.select_related(
            'project_site', 'contractor', 'client',
        ).annotate(
            _paid_total=Coalesce(Sum('contractpayments__price', filter=models.Q(
                contractpayments__made_payment=True)), Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2)),
            _unpaid_total=Coalesce(Sum('contractpayments__price', filter=models.Q(
                contractpayments__made_payment=False)), Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2)),
        )

    def paid_amount(self, obj):
        annotated = getattr(obj, '_paid_total', None)
        if annotated is not None:
            return annotated
        return obj.contractpayments_set.filter(made_payment=True)\
        .aggregate(total=Coalesce(Sum('price'),Value(0), output_field=DecimalField(max_digits=12,decimal_places=2)))['total']

    def unpaid_amount(self, obj):
        annotated = getattr(obj, '_unpaid_total', None)
        if annotated is not None:
            return annotated
        return obj.contractpayments_set.filter(made_payment=False)\
        .aggregate(total=Coalesce(Sum('price'),Value(0), output_field=DecimalField(max_digits=12,decimal_places=2)))['total']

    def status_check(self, obj):
      return obj.price - (self.paid_amount(obj) + self.unpaid_amount(obj))


    paid_amount.short_description = 'Оплаченная сумма'
    unpaid_amount.short_description = 'Неоплаченная сумма'
    status_check.short_description = 'Статус проверки'


class PaymentTaskLinkInline(admin.TabularInline):
    model = PaymentTaskLink
    extra = 0
    fields = ('task_node', 'amount_applied', 'notes')
    autocomplete_fields = ('task_node',)


@admin.register(ContractPayments)
class ContractPaymentsAdmin(admin.ModelAdmin):
    _all_list = ['contract',  'price', 'start_date', 'due_date', 'duration']
    list_display = ['id', 'parent', 'project_site', 'payment_type', 'status', 'made_payment', 'contractor_name', ] + _all_list
    list_filter = [ContractFilter, ProjectSiteFilter,ContractorFilter, PaymentTypeFilter,  'made_payment','start_date']
    search_fields = ['contract__name', 'name']
    list_display_links = ['id', ]
    list_editable = ['parent', 'start_date', 'due_date', 'duration']
    actions = [duplicate_event,]
    inlines = (PaymentTaskLinkInline,)
    form = ContractPaymentsAdminForm
    list_per_page = 10
    change_list_template = 'jazzmin/admin/paymentCalendar.html'

    formfield_overrides = {
        models.TextField: {
            'widget': Textarea(attrs={'cols': 60, 'rows': 2})
        },
    }


    def response_post_save_add(self, request, obj):
        next_url = request.GET.get('_next')
        if next_url:
            return HttpResponseRedirect(next_url)
        return super().response_post_save_add(request, obj)

    def response_post_save_change(self, request, obj):
        next_url = request.GET.get('_next')
        if next_url:
            return HttpResponseRedirect(next_url)
        return super().response_post_save_change(request, obj)

    def changelist_view(self, request, extra_context=None):
        # Один рендер: календарь докладываем в context_data. Ф2: считать ДДС из БД.
        scale, original_get = _extract_scale(request)
        extra_context = extra_context or {}
        try:
            response = super().changelist_view(request, extra_context=extra_context)
        finally:
            request.GET = original_get
        try:
            # Проверяем наличие context_data
            if hasattr(response, 'context_data'):
                qs = response.context_data['cl'].queryset
                filtered_contracts = qs.values_list('contract', flat=True)
                contract_list = Contract.objects.filter(id__in=filtered_contracts).all()
                before = set(extra_context)
                payments = create_payment_calendar(extra_context, scale, all_contracts=contract_list, contract_payment_filter=qs)
                response.context_data.update(
                    {k: v for k, v in payments.items() if k not in before})
        except Exception as e:
            messages.error(request, f" ошибка {e}")

        return response

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        log_change(payment=obj, action='updated' if change else 'created',
                   details=f'{obj.name} ({obj.price})', user=request.user)

    def delete_model(self, request, obj):
        log_change(payment=obj, action='deleted',
                   details=f'{obj.name} (id={obj.pk}, цена={obj.price})',
                   user=request.user)
        super().delete_model(request, obj)


@admin.register(ContractChangeLog)
class ContractChangeLogAdmin(admin.ModelAdmin):
    list_display = ['creation_stamp', 'action', 'contract', 'payment', 'task', 'user']
    list_filter = ['action', 'creation_stamp']
    search_fields = ['details', 'contract__name', 'payment__name', 'task__name']
    date_hierarchy = 'creation_stamp'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(TaskComment)
class TaskCommentAdmin(admin.ModelAdmin):
    """Комментарии к задачам (DMX-3): только чтение."""
    list_display = ['creation_stamp', 'task', 'author', 'body']
    list_filter = ['creation_stamp']
    search_fields = ['body', 'task__name']
    date_hierarchy = 'creation_stamp'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'color', 'description']
    search_fields = ['name']


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ['file', 'task', 'contract', 'uploaded_by', 'creation_stamp']
    list_filter = ['creation_stamp']
    search_fields = ['file', 'task__name', 'contract__name']
    date_hierarchy = 'creation_stamp'

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ContractReminder)
class ContractReminderAdmin(admin.ModelAdmin):
    """Напоминания (DMX-2): кому/когда, флаги отправки и закрытия."""
    list_display = ['due_date', 'contract', 'task', 'payment', 'message',
                    'recipient', 'is_sent', 'is_done']
    list_filter = ['is_sent', 'is_done', 'due_date']
    search_fields = ['message', 'contract__name', 'task__name']
    date_hierarchy = 'due_date'
    list_per_page = 25


@admin.register(ContractStageLog)
class ContractStageLogAdmin(admin.ModelAdmin):
    """Журнал этапов (DMC-5): фильтры stage/date/contract, просмотр без правок."""
    list_display = ['date', 'contract', 'stage_display', 'is_next_step', 'user', 'notes']
    list_filter = ['stage', 'date', 'contract', 'is_next_step']
    search_fields = ['contract__name', 'contract__number', 'notes']
    date_hierarchy = 'date'
    list_per_page = 25

    @admin.display(description='Этап', ordering='stage')
    def stage_display(self, obj):
        return obj.get_stage_display()

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CashflowEntry)
class CashflowEntryAdmin(admin.ModelAdmin):
    """Строки ДДС — только чтение (пересчёт — rebuild_cashflow/сигналы)."""
    list_display = ['date', 'contract', 'payment', 'bucket', 'amount']
    list_filter = ['bucket', 'contract']
    date_hierarchy = 'date'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False



@admin.register(PaymentTaskLink)
class PaymentTaskLinkAdmin(admin.ModelAdmin):
    list_display = ['id', 'payment', 'task_node', 'amount_applied', 'notes']
    list_filter = ['payment__contract', 'payment__status']
    search_fields = ['payment__name', 'task_node__name']
    autocomplete_fields = ('payment', 'task_node')
    list_per_page = 20


class EstimateConceptInline(admin.TabularInline):
    model = EstimateConcept
    extra = 0
    fields = ('name', 'building_number', 'design_chapter', 'amount', 'task_node')
    autocomplete_fields = ('task_node',)


@admin.register(ContractEstimate)
class ContractEstimateAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'contract', 'contractor_name', 'status', 'total_amount', 'is_overrun_flag']
    list_filter = ['status', EstimateContractorFilter, EstimateContractFilter]
    search_fields = ['name', 'contract__name', 'contract__number']
    inlines = (EstimateConceptInline,)
    actions = ('rollup_estimates', 'approve_estimates')
    list_per_page = 20

    @admin.display(description='Подрядчик', ordering='contract__contractor')
    def contractor_name(self, obj):
        return obj.contract.contractor if obj.contract else None

    @admin.display(boolean=True, description='Перерасход')
    def is_overrun_flag(self, obj):
        return obj.is_overrun

    @admin.action(description='Пересчитать итоги смет')
    def rollup_estimates(self, request, queryset):
        for est in queryset:
            est.rollup()
        self.message_user(request, f'Пересчитано смет: {queryset.count()}')

    @admin.action(description='Утвердить сметы')
    def approve_estimates(self, request, queryset):
        updated = queryset.update(status='approved')
        self.message_user(request, f'Утверждено смет: {updated}')


class EstimateTaskLinkInline(admin.TabularInline):
    model = EstimateTaskLink
    fk_name = 'estimate_concept'
    extra = 0
    fields = ('task_node', 'link_type', 'note', 'created_by')
    readonly_fields = ('created_by',)
    autocomplete_fields = ('task_node',)


@admin.register(EstimateConcept)
class EstimateConceptAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'building_number', 'design_chapter', 'contract_name', 'amount', 'act', 'task_node']
    list_filter = ['estimate__status', ConceptContractorFilter, ConceptContractFilter, ConceptEstimateFilter, ConceptActFilter, 'building_number', 'design_chapter']
    search_fields = ['name', 'estimate__name', 'task_node__name', 'act__number']
    fields = ['name', 'building_number', 'design_chapter', 'estimate', 'amount', 'act', 'task_node']
    autocomplete_fields = ('estimate', 'task_node')
    list_per_page = 20
    inlines = (EstimateTaskLinkInline,)
    actions = ('create_tasks_from_concepts',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'estimate__contract__contractor', 'building_number__name',
            'design_chapter', 'act__contract')

    @admin.display(description='Договор', ordering='estimate__contract__name')
    def contract_name(self, obj):
        est = obj.estimate
        return est.contract if est and est.contract else None

    @admin.action(description='Создать задачи из позиций (незакрытые, без задач)')
    def create_tasks_from_concepts(self, request, queryset):
        """Массовое создание задач TaskNode из позиций сметы.

        Только позиции без акта (act__isnull) И без задач (нет связок
        EstimateTaskLink и пустое task_node) — «которых нет сейчас».
        Группировка под родительскую суммарную задачу («<Договор> — работы
        по смете», одна на договор, переиспользуется) — ОПЦИЯ, по умолчанию
        выключена: плоские корневые задачи. Цена родителя = сумме позиций
        под ним. Поле task_node ставится только при первом создании
        (основная задача); все создания фиксируются в EstimateTaskLink.
        """
        from django.shortcuts import render
        from ProjectTDL.services.task_mutations import (
            create_task_with_defaults, get_or_create_contract_summary,
        )

        ids = request.POST.getlist('_selected_action')
        if 'apply' in request.POST and ids:
            group = request.POST.get('group_by_contract') == '1'
            concepts = EstimateConcept.objects.filter(
                pk__in=ids, act__isnull=True).select_related(
                'estimate__contract__contractor',
                'estimate__contract__project_site',
                'building_number', 'design_chapter', 'estimate__contract'
            ).prefetch_related('task_links')
            # Группируем по договору в порядке позиций (стабильно).
            groups = {}
            no_contract, skipped_closed, skipped_linked = 0, 0, 0
            for concept in concepts.order_by('id'):
                est = concept.estimate
                contract = est.contract if est else None
                if contract is None:
                    no_contract += 1
                    continue
                groups.setdefault(contract.pk, (contract, []))[1].append(concept)
            skipped_closed = len(ids) - concepts.count()
            created_parents, created_children = 0, 0
            for contract, group_concepts in groups.values():
                parent = None
                if group:
                    parent, was_created = get_or_create_contract_summary(
                        owner=request.user, contract=contract)
                    if was_created:
                        created_parents += 1
                        log_change(task=parent, action='task:summary_created',
                                   details=f'суммарная задача договора {contract} '
                                           f'для позиций сметы',
                                   user=request.user)
                for concept in group_concepts:
                    if (concept.task_node_id is not None
                            or concept.task_links.exists()):
                        skipped_linked += 1
                        continue
                    task = create_task_with_defaults(
                        owner=request.user,
                        name=(concept.name or '')[:150],
                        project_site_id=contract.project_site_id,
                        contractor_id=contract.contractor_id,
                        building_number_id=concept.building_number_id,
                        parent=parent,
                        node_type='subtask' if group else 'task',
                    )
                    task.design_chapter_id = concept.design_chapter_id
                    task.contract_id = contract.pk
                    task.price = concept.amount or 0
                    task.save(update_fields=['design_chapter', 'contract', 'price'])
                    EstimateTaskLink.objects.get_or_create(
                        estimate_concept=concept, task_node=task,
                        defaults={'link_type': 'created_from',
                                  'created_by': request.user})
                    concept.task_node = task
                    concept.save(update_fields=['task_node'])
                    created_children += 1
                    log_change(task=task, action='task:created_from_estimate',
                               details=f'из позиции сметы {concept.pk} '
                                       f'({concept.estimate})'
                                       + (f', родитель {parent.pk}' if parent else ''),
                               user=request.user)
                if parent is not None:
                    self._refresh_summary_price(parent)
            if group:
                self.message_user(
                    request,
                    f'Родительских задач: {created_parents} (создано), '
                    f'дочерних: {created_children}. Пропущено: закрыты актом — '
                    f'{skipped_closed}, уже с задачами — {skipped_linked}, '
                    f'без договора — {no_contract}.')
            else:
                self.message_user(
                    request,
                    f'Создано задач: {created_children}. Пропущено: закрыты '
                    f'актом — {skipped_closed}, уже с задачами — '
                    f'{skipped_linked}, без договора — {no_contract}.')
            return redirect(request.get_full_path())

        concepts = queryset.select_related(
            'estimate__contract', 'building_number__name', 'design_chapter',
            'act').prefetch_related('task_links').order_by('id')
        rows = []
        for c in concepts:
            est = c.estimate
            contract = est.contract if est else None
            if c.act_id:
                reason = 'пропуск (акт)'
            elif c.task_node_id is not None or c.task_links.exists():
                reason = 'пропуск (есть задачи)'
            elif contract is None:
                reason = 'пропуск (нет договора)'
            else:
                reason = None
            rows.append({
                'concept': c,
                'reason': reason,
                'parent_name': (f'{contract.name} — работы по смете'
                                if contract else '—'),
            })
        return render(request, 'admin/ProjectContract/estimateconcept_create_tasks.html', {
            'concepts': [r['concept'] for r in rows],
            'reasons': {r['concept'].pk: r['reason'] for r in rows},
            'parents': {r['concept'].pk: r['parent_name'] for r in rows},
            'opts': self.model._meta,
            'action': 'create_tasks_from_concepts',
        })

    @staticmethod
    def _refresh_summary_price(parent):
        """Цена родителя = сумме позиций под ним (self-healing при повторах)."""
        from django.db.models import Sum
        child_ids = list(parent.children.values_list('pk', flat=True))
        concept_ids = EstimateTaskLink.objects.filter(
            task_node_id__in=child_ids).values_list('estimate_concept_id', flat=True)
        total = EstimateConcept.objects.filter(
            pk__in=concept_ids).aggregate(total=Sum('amount'))['total'] or 0
        parent.price = total
        parent.save(update_fields=['price'])


@admin.register(Act)
class ActAdmin(admin.ModelAdmin):
    list_display = ['id', 'number', 'act_date', 'contract']
    list_filter = ['contract']
    search_fields = ['number', 'contract__name']
    fields = ['number', 'act_date', 'contract', 'file']
    list_per_page = 20
