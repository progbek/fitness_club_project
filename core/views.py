from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.utils import timezone
from .models import Client, Subscription, SubscriptionType, AccessLog
from .forms import ClientForm, SubscriptionForm, SubscriptionTypeForm
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView
from django.contrib.auth import authenticate, login
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render, redirect
from django.contrib.auth import logout
from django.contrib.auth.models import User, Group
from django.db.models import Count, Sum, Q, F
from datetime import datetime, timedelta
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json
from .templatetags.auth_extras import is_manager, is_administrator
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def subscription_type_clients(request, type_id):
    """API для получения клиентов по типу абонемента"""
    try:
        subscription_type = SubscriptionType.objects.get(pk=type_id)

        # Получаем всех клиентов с этим типом абонемента
        clients = Client.objects.filter(
            subscriptions__type=subscription_type
        ).distinct().select_related()

        clients_data = []
        for client in clients:
            # Получаем активный абонемент этого типа
            active_sub = client.subscriptions.filter(
                type=subscription_type,
                is_active=True
            ).first()

            clients_data.append({
                'id': client.id,
                'first_name': client.first_name,
                'last_name': client.last_name,
                'phone': client.phone,
                'subscription_type': subscription_type.name,
                'is_active': active_sub.is_valid() if active_sub else False
            })

        return JsonResponse({
            'success': True,
            'subscription_type': subscription_type.name,
            'clients': clients_data
        })

    except SubscriptionType.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Тип абонемента не найден'
        })


@csrf_exempt
@require_POST
def turnstile_api(request):
    """API endpoint для взаимодействия с турникетом Hikvision"""
    try:
        data = json.loads(request.body)
        face_id = data.get('face_id')
        device_id = data.get('device_id', 'turnstile_1')

        if not face_id:
            return JsonResponse({
                'success': False,
                'access_granted': False,
                'reason': 'Face ID не предоставлен'
            })

        try:
            client = Client.objects.get(face_id=face_id)
        except Client.DoesNotExist:
            # Логируем попытку входа неизвестного клиента
            AccessLog.objects.create(
                client=None,
                access_granted=False,
                reason=f'Клиент с Face ID {face_id} не найден'
            )
            return JsonResponse({
                'success': False,
                'access_granted': False,
                'reason': 'Клиент не найден'
            })

        # Ищем ЛЮБОЙ активный абонемент с remaining_visits > 0
        active_subscription = None
        for subscription in client.subscriptions.filter(is_active=True):
            if subscription.remaining_visits > 0:
                active_subscription = subscription
                break

        if not active_subscription:
            # Логируем отсутствие активного абонемента
            AccessLog.objects.create(
                client=client,
                access_granted=False,
                reason='Нет активного абонемента с доступными посещениями'
            )
            return JsonResponse({
                'success': False,
                'access_granted': False,
                'reason': 'Нет активного абонемента'
            })

        # Проверяем можно ли получить доступ
        if not active_subscription.can_access_today():
            AccessLog.objects.create(
                client=client,
                access_granted=False,
                reason='Доступ запрещен системой'
            )
            return JsonResponse({
                'success': False,
                'access_granted': False,
                'reason': 'Доступ запрещен'
            })

        # Отмечаем доступ (списываем посещение если нужно)
        was_deducted = active_subscription.mark_access()

        # Логируем успешный проход
        AccessLog.objects.create(
            client=client,
            access_granted=True,
            reason=f'Успешный проход через {device_id}' +
                  (' (списано посещение)' if was_deducted else ' (повторный вход)')
        )

        return JsonResponse({
            'success': True,
            'access_granted': True,
            'was_deducted': was_deducted,
            'client': {
                'id': client.id,
                'first_name': client.first_name,
                'last_name': client.last_name,
                'photo_url': client.photo.url if client.photo else None,
            },
            'subscription': {
                'type': active_subscription.type.name,
                'remaining_visits': active_subscription.remaining_visits,
                'total_visits': active_subscription.paid_visits,
                'used_visits': active_subscription.used_visits,
            }
        })

    except Exception as e:
        # Логируем ошибку сервера
        AccessLog.objects.create(
            client=None,
            access_granted=False,
            reason=f'Ошибка сервера: {str(e)}'
        )
        return JsonResponse({
            'success': False,
            'access_granted': False,
            'reason': f'Ошибка сервера: {str(e)}'
        })


@login_required
@user_passes_test(is_manager)
def turnstile_test(request):
    """Тестовая страница для проверки работы турникета"""
    clients = Client.objects.all().order_by('last_name', 'first_name')
    return render(request, 'core/turnstile_test.html', {
        'clients': clients
    })


def can_manage_clients(user):
    """Проверяет, может ли пользователь управлять клиентами (кассиры, руководители, администраторы)"""
    return is_cashier(user) or is_manager(user) or is_administrator(user)


def can_manage_staff(user):
    """Проверяет, может ли пользователь управлять персоналом"""
    return is_manager(user)

def can_manage_subscriptions(user):
    """Проверяет, может ли пользователь управлять абонементами (кассиры, руководители, администраторы)"""
    return is_cashier(user) or is_manager(user) or is_administrator(user)

def custom_login(request):
    """Кастомный view для входа"""
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('core:index')
    else:
        form = AuthenticationForm()

    return render(request, 'registration/login.html', {'form': form})


def custom_logout(request):
    """Кастомный view для выхода"""
    logout(request)
    return render(request, 'registration/logged_out.html')


class CustomLoginView(auth_views.LoginView):
    template_name = 'registration/login.html'  # Новый путь


class CustomLogoutView(auth_views.LogoutView):
    template_name = 'registration/logged_out.html'  # Новый путь


class LoginSuccessView(TemplateView):
    template_name = 'core/auth/login_success.html'


# Функции-проверки прав
def is_cashier(user):
    """Проверяет, является ли пользователь кассиром"""
    if not user.is_authenticated:
        return False
    return user.groups.filter(name__in=['Кассиры', 'Cashiers']).exists()

@login_required
@user_passes_test(can_manage_staff)
def cashier_list(request):
    """Список всех кассиров"""
    cashiers_group = Group.objects.get(name='Кассиры')
    cashiers = cashiers_group.user_set.all().order_by('username')

    return render(request, 'core/cashier_list.html', {
        'cashiers': cashiers
    })


@login_required
@user_passes_test(can_manage_staff)
def cashier_create(request):
    """Создание нового кассира"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Пользователь с таким именем уже существует!')
        else:
            user = User.objects.create_user(username=username, password=password)
            cashiers_group = Group.objects.get(name='Кассиры')
            user.groups.add(cashiers_group)
            messages.success(request, f'Кассир {username} успешно создан!')
            return redirect('core:cashier_list')

    return render(request, 'core/cashier_form.html', {
        'title': 'Добавить кассира'
    })


@login_required
@user_passes_test(can_manage_staff)
def cashier_delete(request, pk):
    """Удаление кассира"""
    cashier = get_object_or_404(User, pk=pk)

    if request.method == 'POST':
        username = cashier.username
        cashier.delete()
        messages.success(request, f'Кассир {username} успешно удален!')
        return redirect('core:cashier_list')

    return render(request, 'core/cashier_confirm_delete.html', {
        'cashier': cashier
    })


# Главная страница
def index(request):
    """Главная страница - для кассиров показывает журнал проходов"""
    if not request.user.is_authenticated:
        return render(request, 'core/index.html')

    # Если пользователь кассир - перенаправляем на журнал проходов
    if is_cashier(request.user):
        return redirect('core:access_logs')
    elif is_manager(request.user) or is_administrator(request.user):
        # Для руководителей и администраторов показываем обычную главную страницу
        context = {}
        # Статистика для руководителя
        today_logs = AccessLog.objects.filter(timestamp__date=timezone.now().date())
        context['today_visits'] = today_logs.count()
        context['today_access_granted'] = today_logs.filter(access_granted=True).count()
        return render(request, 'core/index.html', context)
    else:
        # Для остальных пользователей (если есть) - перенаправляем на логин
        return redirect('core:login')


# Список всех клиентов
@login_required
@user_passes_test(can_manage_clients)
def client_list(request):
    """Список всех клиентов с поиском и сортировкой"""
    # Сначала получаем всех клиентов и сортируем как QuerySet
    clients = Client.objects.all().order_by('last_name', 'first_name')

    # Поиск по имени, фамилии или телефону (НЕЧУВСТВИТЕЛЬНЫЙ К РЕГИСТРУ)
    search_query = request.GET.get('search', '').strip()
    if search_query:
        search_lower = search_query.lower()
        # Фильтрация в Python - гарантированно нечувствительно к регистру
        filtered_clients = []
        for client in clients:
            if (search_lower in (client.first_name or '').lower() or
                    search_lower in (client.last_name or '').lower() or
                    search_lower in (client.phone or '').lower() or
                    search_lower in (client.face_id or '').lower()):
                filtered_clients.append(client)
        clients = filtered_clients
    else:
        # Если нет поиска, просто используем отсортированный QuerySet
        clients = list(clients)  # Конвертируем в список для consistency

    # Сортировка (теперь clients всегда список)
    sort_by = request.GET.get('sort', 'name')
    if sort_by == 'date':
        clients.sort(key=lambda x: x.date_created, reverse=True)
    elif sort_by == 'subscription':
        clients.sort(
            key=lambda x: (
                not any(sub.is_active and sub.paid_visits > sub.used_visits
                        for sub in x.subscriptions.all()),
                x.last_name.lower(),
                x.first_name.lower()
            )
        )
    else:
        # Сортировка по алфавиту (по умолчанию)
        clients.sort(key=lambda x: (x.last_name.lower(), x.first_name.lower()))

    return render(request, 'core/client_list.html', {
        'clients': clients,
        'search_query': search_query,
        'current_sort': sort_by
    })


# Детальная информация о клиенте
@login_required
@user_passes_test(can_manage_clients)
def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk)

    # Получаем ВСЕ абонементы клиента - ИСПРАВЛЯЕМ сортировку!
    subscriptions = client.subscriptions.all().order_by('-purchase_date')  # Было: '-start_date'

    # Определяем активный абонемент
    active_subscription = None
    for subscription in subscriptions:
        if subscription.is_valid():
            active_subscription = subscription
            break

    return render(request, 'core/client_detail.html', {
        'client': client,
        'subscriptions': subscriptions,
        'active_subscription': active_subscription
    })


# Добавление нового клиента
@login_required
@user_passes_test(can_manage_clients)
def client_create(request):
    if request.method == 'POST':
        form = ClientForm(request.POST, request.FILES)
        if form.is_valid():
            new_client = form.save()
            messages.success(request, f'Клиент {new_client} успешно добавлен!')
            return redirect('core:client_detail', pk=new_client.pk)
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
    else:
        form = ClientForm()

    return render(request, 'core/client_form.html', {'form': form, 'title': 'Добавить клиента'})


@login_required
@user_passes_test(lambda u: is_manager(u) or is_administrator(u))
def client_update(request, pk):
    """Редактирование клиента"""
    client = get_object_or_404(Client, pk=pk)

    if request.method == 'POST':
        form = ClientForm(request.POST, request.FILES, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, f'Данные клиента {client} успешно обновлены!')
            return redirect('core:client_detail', pk=client.pk)
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
    else:
        form = ClientForm(instance=client)

    return render(request, 'core/client_form.html', {
        'form': form,
        'client': client,
        'title': f'Редактировать клиента: {client}'
    })


@login_required
@user_passes_test(lambda u: is_manager(u) or is_administrator(u))
def client_delete(request, pk):
    """Удаление клиента"""
    client = get_object_or_404(Client, pk=pk)

    if request.method == 'POST':
        client_name = str(client)
        client.delete()
        messages.success(request, f'Клиент {client_name} успешно удален!')
        return redirect('core:client_list')

    return render(request, 'core/client_confirm_delete.html', {
        'client': client
    })


# Журнал проходов - только для руководителей

@login_required
@user_passes_test(lambda u: is_cashier(u) or is_manager(u) or is_administrator(u))
def access_logs(request):
    """Просмотр логов проходов с фильтрацией по дате"""
    selected_date_str = request.GET.get('date')
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = timezone.now().date()
    else:
        selected_date = timezone.now().date()

    # Фильтруем логи по выбранной дате
    logs = AccessLog.objects.filter(
        timestamp__date=selected_date
    ).order_by('-timestamp')

    # Статистика для отображения
    successful_count = AccessLog.objects.filter(access_granted=True).count()
    denied_count = AccessLog.objects.filter(access_granted=False).count()
    total_count = AccessLog.objects.count()

    # Статистика за выбранный день
    today_successful = logs.filter(access_granted=True).count()
    today_denied = logs.filter(access_granted=False).count()
    today_total = logs.count()

    # Генерируем список дат для выпадающего списка (последние 30 дней)
    date_options = []
    for i in range(30):
        date = timezone.now().date() - timedelta(days=i)
        date_options.append(date)

    context = {
        'logs': logs,
        'successful_count': successful_count,
        'denied_count': denied_count,
        'total_count': total_count,
        'today_successful': today_successful,
        'today_denied': today_denied,
        'today_total': today_total,
        'selected_date': selected_date,
        'date_options': date_options,
    }

    return render(request, 'core/access_logs.html', context)


@login_required
@user_passes_test(can_manage_subscriptions)
def subscription_create(request, client_pk):
    """Добавление нового абонемента клиенту"""
    client = get_object_or_404(Client, pk=client_pk)

    if request.method == 'POST':
        form = SubscriptionForm(request.POST)
        if form.is_valid():
            # СОЗДАЕМ АБОНЕМЕНТ ПРАВИЛЬНО - без form.save(commit=False)
            subscription = Subscription(
                client=client,
                type=form.cleaned_data['type'],
                # Явно указываем начальные значения
                paid_visits=form.cleaned_data['type'].duration_days,  # <- Вот это ОЧЕНЬ важно!
                used_visits=0,
                is_active=True,
                purchase_date=timezone.now()
            )
            subscription.save()

            messages.success(request, f'Абонемент "{subscription.type}" успешно добавлен для {client}!')
            return redirect('core:client_detail', pk=client.pk)
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
    else:
        form = SubscriptionForm()

    return render(request, 'core/subscription_form.html', {
        'form': form,
        'client': client,
        'title': f'Добавить абонемент для {client}'
    })


@login_required
@user_passes_test(lambda u: is_manager(u) or is_administrator(u))
def subscriptiontype_list(request):
    """Список всех типов абонементов"""
    subscription_types = SubscriptionType.objects.all().order_by('name')
    return render(request, 'core/subscriptiontype_list.html', {
        'subscription_types': subscription_types
    })


@csrf_exempt
@require_POST
def process_turnstile_event(request):
    """Обработка события от турникета (будет вызываться по API)"""
    try:
        # Здесь будет получать face_id от турникета
        face_id = request.POST.get('face_id')

        if not face_id:
            return JsonResponse({'success': False, 'error': 'No face_id provided'})

        # Ищем клиента по face_id
        try:
            client = Client.objects.get(face_id=face_id)
        except Client.DoesNotExist:
            # Создаем запись в логе о неудачной попытке
            AccessLog.objects.create(
                client=None,
                access_granted=False,
                reason='Клиент не найден в системе'
            )
            return JsonResponse({'success': False, 'error': 'Client not found'})

        # Ищем активный абонемент
        active_subscription = None
        for subscription in client.subscriptions.all():
            if subscription.is_valid():
                active_subscription = subscription
                break

        if not active_subscription:
            # Нет активного абонемента
            AccessLog.objects.create(
                client=client,
                access_granted=False,
                reason='Нет активного абонемента'
            )
            return JsonResponse({'success': False, 'error': 'No active subscription'})

        # Проверяем остаток дней
        if active_subscription.remaining_days <= 0:
            AccessLog.objects.create(
                client=client,
                access_granted=False,
                reason='Закончились дни по абонементу'
            )
            return JsonResponse({'success': False, 'error': 'No days left'})

        # Все проверки пройдены - разрешаем проход
        active_subscription.mark_visit()  # Используем один день

        AccessLog.objects.create(
            client=client,
            access_granted=True,
            reason='Успешный проход'
        )

        return JsonResponse({
            'success': True,
            'client': {
                'first_name': client.first_name,
                'last_name': client.last_name,
                'photo_url': client.photo.url if client.photo else None,
            },
            'subscription': {
                'remaining_days': active_subscription.remaining_days,
                'total_days': active_subscription.paid_days,
                'used_days': active_subscription.used_days
            }
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(lambda u: is_manager(u) or is_administrator(u))
def subscriptiontype_create(request):
    """Создание нового типа абонемента"""
    if request.method == 'POST':
        form = SubscriptionTypeForm(request.POST)
        if form.is_valid():
            subscription_type = form.save()
            messages.success(request, f'Тип абонемента "{subscription_type.name}" успешно создан!')
            return redirect('core:subscriptiontype_list')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
    else:
        form = SubscriptionTypeForm()

    return render(request, 'core/subscriptiontype_form.html', {
        'form': form,
        'title': 'Добавить тип абонемента'
    })


@login_required
@user_passes_test(lambda u: is_manager(u) or is_administrator(u))
def subscriptiontype_update(request, pk):
    """Редактирование типа абонемента"""
    subscription_type = get_object_or_404(SubscriptionType, pk=pk)

    if request.method == 'POST':
        form = SubscriptionTypeForm(request.POST, instance=subscription_type)
        if form.is_valid():
            subscription_type = form.save()
            messages.success(request, f'Тип абонемента "{subscription_type.name}" успешно обновлен!')
            return redirect('core:subscriptiontype_list')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
    else:
        form = SubscriptionTypeForm(instance=subscription_type)

    return render(request, 'core/subscriptiontype_form.html', {
        'form': form,
        'title': f'Редактировать: {subscription_type.name}',
        'subscription_type': subscription_type
    })


@login_required
@user_passes_test(lambda u: is_manager(u) or is_administrator(u))
def subscriptiontype_delete(request, pk):
    """Удаление типа абонемента"""
    subscription_type = get_object_or_404(SubscriptionType, pk=pk)

    # Проверяем, не используется ли тип в активных абонементах
    active_subscriptions = Subscription.objects.filter(type=subscription_type, is_active=True)

    if request.method == 'POST':
        if active_subscriptions.exists():
            messages.error(request,
                           f'Нельзя удалить тип "{subscription_type.name}", так как он используется в активных абонементах!')
            return redirect('core:subscriptiontype_list')

        subscription_type_name = subscription_type.name
        subscription_type.delete()
        messages.success(request, f'Тип абонемента "{subscription_type_name}" успешно удален!')
        return redirect('core:subscriptiontype_list')

    return render(request, 'core/subscriptiontype_confirm_delete.html', {
        'subscription_type': subscription_type,
        'active_subscriptions_count': active_subscriptions.count()
    })


# core/views.py - добавьте эти функции для отчетов
@login_required
@user_passes_test(is_manager)
def reports_dashboard(request):
    """Дашборд с основными отчетами"""

    # Статистика за последние 30 дней
    thirty_days_ago = timezone.now() - timedelta(days=30)

    # Основная статистика
    total_clients = Client.objects.count()
    new_clients = Client.objects.filter(date_created__gte=thirty_days_ago).count()

    # Статистика по посещениям
    total_visits = AccessLog.objects.count()
    successful_visits = AccessLog.objects.filter(access_granted=True).count()
    denied_visits = AccessLog.objects.filter(access_granted=False).count()

    # Статистика по абонементам
    active_subscriptions = Subscription.objects.filter(
        is_active=True,
        paid_visits__gt=F('used_visits')
    ).count()

    expired_subscriptions = Subscription.objects.filter(
        is_active=True,
        paid_visits__lte=F('used_visits')
    ).count()

    # Посещения по дням (последние 7 дней)
    visits_by_day = []
    for i in range(7):
        day = timezone.now() - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)

        day_visits = AccessLog.objects.filter(
            timestamp__range=(day_start, day_end)
        ).count()

        visits_by_day.append({
            'date': day_start.date(),
            'visits': day_visits
        })

    visits_by_day.reverse()  # Чтобы шло от старых к новым

    context = {
        'total_clients': total_clients,
        'new_clients': new_clients,
        'total_visits': total_visits,
        'successful_visits': successful_visits,
        'denied_visits': denied_visits,
        'active_subscriptions': active_subscriptions,
        'expired_subscriptions': expired_subscriptions,
        'visits_by_day': visits_by_day,
    }

    return render(request, 'core/reports_dashboard.html', context)


@login_required
@user_passes_test(is_manager)
def report_finance(request):
    """Финансовый отчет по типам абонементов за последние 30 дней"""
    from django.db.models import Sum, Count

    # Определяем дату 30 дней назад
    thirty_days_ago = timezone.now() - timedelta(days=30)

    # Получаем данные только за последние 30 дней
    revenue_by_type = Subscription.objects.filter(
        purchase_date__gte=thirty_days_ago
    ).values(
        'type__id', 'type__name'
    ).annotate(
        revenue_30_days=Sum('type__price'),  # Доход за 30 дней
        unique_clients=Count('client', distinct=True),  # Уникальных клиентов
    ).order_by('-revenue_30_days')

    # Общий доход за 30 дней
    total_revenue_30_days = sum(item['revenue_30_days'] or 0 for item in revenue_by_type)

    # Общее количество уникальных клиентов за 30 дней
    total_clients_30_days = sum(item['unique_clients'] for item in revenue_by_type)

    # Доход за сегодня
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_revenue = Subscription.objects.filter(
        purchase_date__gte=today_start
    ).aggregate(total=Sum('type__price'))['total'] or 0

    # Доход за последние 30 дней (общая сумма)
    recent_revenue = Subscription.objects.filter(
        purchase_date__gte=thirty_days_ago
    ).aggregate(total=Sum('type__price'))['total'] or 0

    context = {
        'revenue_by_type': revenue_by_type,
        'total_revenue_30_days': total_revenue_30_days,
        'total_clients_30_days': total_clients_30_days,
        'recent_revenue': recent_revenue,
        'today_revenue': today_revenue,
        'today_date': timezone.now().date(),
        'thirty_days_ago': thirty_days_ago.date(),
    }

    return render(request, 'core/report_finance.html', context)


# ДОБАВЛЯЕМ НОВУЮ ФУНКЦИЮ ПЕРЕД report_attendance (или в конец файла)
@require_GET
def subscription_type_clients(request, type_id):
    """API для получения клиентов по типу абонемента"""
    try:
        subscription_type = SubscriptionType.objects.get(pk=type_id)

        # Получаем всех клиентов с этим типом абонемента
        clients = Client.objects.filter(
            subscriptions__type=subscription_type
        ).distinct()

        clients_data = []
        for client in clients:
            # Получаем активный абонемент этого типа
            active_sub = client.subscriptions.filter(
                type=subscription_type,
                is_active=True
            ).first()

            clients_data.append({
                'id': client.id,
                'first_name': client.first_name,
                'last_name': client.last_name,
                'phone': client.phone or 'не указан',
                'email': client.email or 'не указан',
                'date_created': client.date_created.strftime('%d.%m.%Y') if client.date_created else '',
                'subscription_type': subscription_type.name,
                'is_active': active_sub.is_valid() if active_sub else False
            })

        return JsonResponse({
            'success': True,
            'subscription_type': subscription_type.name,
            'clients': clients_data
        })

    except SubscriptionType.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Тип абонемента не найден'
        })

@login_required
@user_passes_test(is_manager)
def report_attendance(request):
    """Отчет по посещаемости"""
    from collections import defaultdict
    from datetime import datetime, timedelta

    # Посещаемость по дням недели
    attendance_by_weekday = defaultdict(int)
    attendance_by_hour = defaultdict(int)

    for log in AccessLog.objects.filter(access_granted=True):
        weekday = log.timestamp.weekday()  # 0=Monday, 6=Sunday
        hour = log.timestamp.hour
        attendance_by_weekday[weekday] += 1
        attendance_by_hour[hour] += 1

    # Конвертируем в удобный формат
    weekdays = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
    attendance_weekday = [{'day': weekdays[i], 'count': attendance_by_weekday[i]} for i in range(7)]

    attendance_hour = [{'hour': f'{h:02d}:00', 'count': attendance_by_hour[h]} for h in range(24)]

    # Самые активные клиенты
    active_clients = Client.objects.annotate(
        visit_count=Count('access_logs', filter=Q(access_logs__access_granted=True))
    ).order_by('-visit_count')[:10]

    context = {
        'attendance_weekday': attendance_weekday,
        'attendance_hour': attendance_hour,
        'active_clients': active_clients,
    }

    return render(request, 'core/report_attendance.html', context)