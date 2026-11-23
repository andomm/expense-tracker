from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_out
from django.db.models.signals import post_save
from django.dispatch import receiver

from .default_categories import seed_user_default_categories
from .logout_marker import record_logout


@receiver(post_save, sender=User, dispatch_uid="expenses.seed_default_categories")
def seed_default_categories_for_new_user(sender, instance, created, **kwargs):
    if created:
        seed_user_default_categories(instance)


user_logged_out.connect(record_logout, dispatch_uid="expenses.record_logout")
