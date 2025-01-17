from django import template
from django.db.models import Sum, DecimalField, Value
from django.db.models.functions import Coalesce
register = template.Library()

@register.simple_tag
def admin_sum(queryset, field_name):
    if field_name == 'total_price':
      return sum(getattr(obj, 'price', 0) for obj in queryset)
    total = queryset.aggregate(total=Coalesce(Sum(field_name), Value(0), output_field=DecimalField()))['total']
    return total or 0