from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self) -> None:
        from django.contrib.auth.signals import user_logged_in, user_login_failed

        from core import signals

        user_logged_in.connect(signals.log_login_success)
        user_login_failed.connect(signals.log_login_failure)
