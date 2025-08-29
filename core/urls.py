# core/urls.py
from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from .views import custom_login, custom_logout

app_name = 'core'

urlpatterns = [
    path('', views.index, name='index'),
    path('clients/', views.client_list, name='client_list'),
    path('client/<int:pk>/', views.client_detail, name='client_detail'),
    path('client/new/', views.client_create, name='client_create'),
    path('access-logs/', views.access_logs, name='access_logs'),
    path('client/<int:client_pk>/subscription/new/', views.subscription_create, name='subscription_create'),
    path('subscription-types/', views.subscriptiontype_list, name='subscriptiontype_list'),
    path('api/turnstile-event/', views.process_turnstile_event, name='turnstile_event'),
    path('subscription-types/', views.subscriptiontype_list, name='subscriptiontype_list'),
    path('subscription-types/new/', views.subscriptiontype_create, name='subscriptiontype_create'),
    path('subscription-types/<int:pk>/edit/', views.subscriptiontype_update, name='subscriptiontype_update'),
    path('subscription-types/<int:pk>/delete/', views.subscriptiontype_delete, name='subscriptiontype_delete'),
    path('accounts/login/', custom_login, name='login'),
    path('accounts/logout/', custom_logout, name='logout'),
    path('client/<int:pk>/edit/', views.client_update, name='client_update'),
    path('client/<int:pk>/delete/', views.client_delete, name='client_delete'),
    path('cashiers/', views.cashier_list, name='cashier_list'),
    path('cashiers/new/', views.cashier_create, name='cashier_create'),
    path('cashiers/<int:pk>/delete/', views.cashier_delete, name='cashier_delete'),
    path('reports/', views.reports_dashboard, name='reports_dashboard'),
    path('reports/finance/', views.report_finance, name='report_finance'),
    path('reports/attendance/', views.report_attendance, name='report_attendance'),
    path('api/turnstile/', views.turnstile_api, name='turnstile_api'),
    path('turnstile-test/', views.turnstile_test, name='turnstile_test'),
    path('api/subscription-type/<int:type_id>/clients/', views.subscription_type_clients, name='subscription_type_clients'),
]