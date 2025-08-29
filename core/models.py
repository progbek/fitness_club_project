from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Client(models.Model):
    # Связь с пользователем Django (для входа в систему, если нужно)
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)

    # Данные клиента
    first_name = models.CharField(max_length=100, verbose_name='Имя')
    last_name = models.CharField(max_length=100, verbose_name='Фамилия')
    photo = models.ImageField(upload_to='client_photos/', verbose_name='Фотография')
    phone = models.CharField(max_length=20, blank=True, verbose_name='Телефон')
    email = models.EmailField(blank=True, verbose_name='Email')
    # ID лица, зарегистрированного в турникете. КРИТИЧЕСКИ ВАЖНОЕ ПОЛЕ.
    face_id = models.CharField(max_length=100, unique=True, db_index=True, verbose_name='Face ID')
    notes = models.TextField(blank=True, verbose_name='Заметки')
    date_created = models.DateTimeField(auto_now_add=True, verbose_name='Дата регистрации')

    class Meta:
        verbose_name = 'Клиент'
        verbose_name_plural = 'Клиенты'

    def get_active_subscription(self):
        """Возвращает активный абонемент клиента"""
        for subscription in self.subscriptions.all():
            if subscription.is_valid():
                return subscription
        return None

    def __str__(self):
        return f"{self.last_name} {self.first_name}"


class SubscriptionType(models.Model):
    name = models.CharField(max_length=50, verbose_name='Название')  # "Standard", "Premium", "Trial"
    is_unlimited = models.BooleanField(default=False, verbose_name='Бессрочный')  # Для бесплатных
    duration_days = models.PositiveIntegerField(default=30, verbose_name='Длительность (дней)')
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name='Цена')

    class Meta:
        verbose_name = 'Тип абонемента'
        verbose_name_plural = 'Типы абонементов'

    def __str__(self):
        return self.name


class Subscription(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='subscriptions', verbose_name='Клиент')
    type = models.ForeignKey(SubscriptionType, on_delete=models.PROTECT, verbose_name='Тип абонемента')
    # Только новые поля:
    purchase_date = models.DateTimeField(default=timezone.now, verbose_name='Дата покупки')
    paid_visits = models.PositiveIntegerField(default=0, verbose_name='Оплачено посещений')
    used_visits = models.PositiveIntegerField(default=0, verbose_name='Использовано посещений')
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    last_visit = models.DateTimeField(null=True, blank=True, verbose_name='Последнее посещение')
    last_access_date = models.DateField(null=True, blank=True, verbose_name='Дата последнего доступа')

    class Meta:
        verbose_name = 'Абонемент'
        verbose_name_plural = 'Абонементы'

    @property
    def remaining_visits(self):
        """Количество оставшихся посещений"""
        return max(0, self.paid_visits - self.used_visits)

    def is_valid(self):
        """Проверяем, действует ли абонемент (есть ли посещения)"""
        if not self.is_active:
            return False
        return self.remaining_visits > 0

    # Убираем декоратор @property и делаем обычным методом
    is_valid.boolean = True
    is_valid.short_description = 'Действителен'

    def mark_visit(self):
        """Отметить посещение (использовать одно посещение)"""
        if self.remaining_visits > 0:
            self.used_visits += 1
            self.last_visit = timezone.now()
            self.save()
            return True
        return False

    def add_visits(self, additional_visits):
        """Добавить дополнительные посещения (продление)"""
        if additional_visits > 0:
            self.paid_visits += additional_visits
            self.save()
            return True
        return False


    def can_access_today(self):
        """Проверяет, можно ли получить доступ сегодня"""
        from django.utils import timezone

        today = timezone.now().date()

        # Если абонемент неактивен - доступ запрещен
        if not self.is_active:
            return False

        # Если закончились посещения - доступ запрещен
        if self.remaining_visits <= 0:
            return False

        # Если уже был доступ сегодня - разрешаем (повторный вход)
        if self.last_access_date == today:
            return True

        # Если это первый вход сегодня - разрешаем
        return True

    def mark_access(self):
        """Отмечает использование доступа на сегодня"""
        from django.utils import timezone

        today = timezone.now().date()
        was_deducted = False

        # Если сегодня еще не было доступа - списываем посещение
        if self.last_access_date != today:
            self.used_visits += 1
            self.last_access_date = today
            was_deducted = True

        # Всегда обновляем время последнего визита
        self.last_visit = timezone.now()
        self.save()

        return was_deducted

    def __str__(self):
        status = "Активен" if self.is_valid() else "Неактивен"
        return f"{self.client} - {self.type} ({self.used_visits}/{self.paid_visits}) - {status}"


# Модель для хранения каждого прохода
class AccessLog(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='access_logs', verbose_name='Клиент')
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name='Время прохода')
    # Успешен ли был проход (прошел ли турникет)
    access_granted = models.BooleanField(default=False, verbose_name='Доступ разрешен')
    # Причина отказа (если access_granted=False)
    reason = models.CharField(max_length=255, blank=True, verbose_name='Причина отказа')

    class Meta:
        verbose_name = 'Лог прохода'
        verbose_name_plural = 'Логи проходов'
        ordering = ['-timestamp']  # Сортировка по убыванию времени (новые сверху)

    def __str__(self):
        status = "Разрешен" if self.access_granted else "Запрещен"
        return f"{self.client} - {self.timestamp} ({status})"


class TelegramUser(models.Model):
    """Модель для хранения Telegram пользователей"""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    chat_id = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=100, blank=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Telegram пользователь'
        verbose_name_plural = 'Telegram пользователи'

    def __str__(self):
        return f"{self.username} ({self.chat_id})"