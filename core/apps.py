# core/apps.py
from django.apps import AppConfig
import os
import subprocess
import sys
from django.conf import settings


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        """
        Запускаем Telegram бота при запуске Django.
        """
        # Не запускаем в dev режиме (чтобы избежать двойного запуска)
        if settings.DEBUG and os.environ.get('RUN_MAIN'):
            return

        if not settings.TELEGRAM_BOT_TOKEN:
            print("🤖 Telegram bot: Token not set, skipping...")
            return

        try:
            print("🤖 Starting Telegram bot...")

            # Запускаем бота в отдельном процессе
            bot_script = os.path.join(os.path.dirname(__file__), '..', 'run_bot.py')
            subprocess.Popen([sys.executable, bot_script])

        except Exception as e:
            print(f"🤖 Failed to start bot: {e}")