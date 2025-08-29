from django import forms
from .models import Client, Subscription, SubscriptionType
from django.utils import timezone


# В классе ClientForm добавим widgets с классами:
class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['first_name', 'last_name', 'photo', 'phone', 'email', 'face_id', 'notes']
        labels = {
            'first_name': 'Имя',
            'last_name': 'Фамилия',
            'photo': 'Фотография',
            'phone': 'Телефон',
            'email': 'Email',
            'face_id': 'Face ID',
            'notes': 'Заметки',
        }
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Введите имя'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Введите фамилию'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+7 (XXX) XXX-XX-XX'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@example.com'}),
            'face_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Уникальный идентификатор'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Дополнительная информация...'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }


class SubscriptionForm(forms.ModelForm):
    class Meta:
        model = Subscription
        fields = ['type', 'purchase_date']
        labels = {
            'type': 'Тип абонемента',
            'purchase_date': 'Дата покупки',
        }
        widgets = {
            'purchase_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['type'].queryset = SubscriptionType.objects.all()
        self.fields['purchase_date'].initial = timezone.now().date()


# core/forms.py - ДОБАВЬТЕ эту форму в конец файла
class SubscriptionTypeForm(forms.ModelForm):
    class Meta:
        model = SubscriptionType
        fields = ['name', 'is_unlimited', 'duration_days', 'price']
        labels = {
            'name': 'Название',
            'is_unlimited': 'Бессрочный',
            'duration_days': 'Длительность (дней)',
            'price': 'Цена',
        }
        widgets = {
            'duration_days': forms.NumberInput(attrs={'min': 1, 'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Делаем поле длительности необязательным для бессрочных абонементов
        self.fields['duration_days'].required = False

    def clean(self):
        cleaned_data = super().clean()
        is_unlimited = cleaned_data.get('is_unlimited')
        duration_days = cleaned_data.get('duration_days')

        # Для небессрочных абонементов проверяем, что указана длительность
        if not is_unlimited and not duration_days:
            raise forms.ValidationError('Для ограниченного абонемента необходимо указать длительность')

        return cleaned_data