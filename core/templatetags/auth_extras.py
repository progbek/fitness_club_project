from django import template

register = template.Library()

@register.filter(name='is_cashier')
def is_cashier(user):
    """Проверяет, является ли пользователь кассиром"""
    if not user.is_authenticated:
        return False
    return user.groups.filter(name__in=['Кассиры', 'Cashiers']).exists()

@register.filter(name='is_manager')
def is_manager(user):
    """Проверяет, является ли пользователь руководителем"""
    if not user.is_authenticated:
        return False
    return user.groups.filter(name__in=['Руководитель', 'Managers']).exists()

@register.filter(name='is_administrator')
def is_administrator(user):
    """Проверяет, является ли пользователь администратором"""
    if not user.is_authenticated:
        return False
    return user.groups.filter(name__in=['Администраторы', 'Administrators']).exists()