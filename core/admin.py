from django.contrib import admin
from .models import Client, SubscriptionType, Subscription, AccessLog


class SubscriptionInline(admin.TabularInline):
    model = Subscription
    extra = 0
    readonly_fields = ('remaining_visits', 'is_valid', 'last_visit')
    fields = (
        'type', 'purchase_date', 'paid_visits', 'used_visits', 'remaining_visits', 'is_active', 'is_valid',
        'last_visit')


class ClientAdmin(admin.ModelAdmin):
    list_display = ('last_name', 'first_name', 'phone', 'date_created')
    list_filter = ('date_created',)
    search_fields = ('last_name', 'first_name', 'phone', 'face_id')
    inlines = [SubscriptionInline]


class SubscriptionTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_unlimited', 'duration_days', 'price')
    list_filter = ('is_unlimited',)


class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        'client', 'type', 'purchase_date', 'paid_visits', 'used_visits', 'remaining_visits', 'is_active', 'is_valid',
        'last_visit')
    list_filter = ('type', 'is_active', 'purchase_date')
    readonly_fields = ('remaining_visits', 'is_valid', 'last_visit')  # УБРАЛИ used_visits ОТСЮДА
    fieldsets = (
        (None, {
            'fields': ('client', 'type', 'is_active')
        }),
        ('Посещения', {
            'fields': ('purchase_date', 'paid_visits', 'used_visits', 'remaining_visits', 'last_visit')
        }),
        ('Статус', {
            'fields': ('is_valid',)
        })
    )

    def remaining_visits(self, obj):
        return obj.remaining_visits

    remaining_visits.short_description = 'Осталось посещений'


class AccessLogAdmin(admin.ModelAdmin):
    list_display = ('client', 'timestamp', 'access_granted', 'reason')
    list_filter = ('access_granted', 'timestamp')
    readonly_fields = ('timestamp',)
    search_fields = ('client__last_name', 'client__first_name', 'client__face_id')


# Регистрируем наши модели с обновленными настройками
admin.site.register(Client, ClientAdmin)
admin.site.register(SubscriptionType, SubscriptionTypeAdmin)
admin.site.register(Subscription, SubscriptionAdmin)
admin.site.register(AccessLog, AccessLogAdmin)

# Добавляем кастомные заголовки для админки
admin.site.site_header = 'Панель администратора Фитнес-клуба'
admin.site.site_title = 'Фитнес-клуб'
admin.site.index_title = 'Управление системой'
