from django import template

register = template.Library()

@register.filter
def multiply(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def subtract(value, arg):
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def divide(value, arg):
    try:
        if float(arg) == 0:
            return 0
        return float(value) / float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def min_val(value, arg):
    try:
        return min(float(value), float(arg))
    except (ValueError, TypeError):
        return value

@register.filter
def abs_val(value):
    try:
        return abs(float(value))
    except (ValueError, TypeError):
        return 0

