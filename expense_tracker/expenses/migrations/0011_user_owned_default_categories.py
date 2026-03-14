from django.db import migrations


def _category_depth(category):
    depth = 1
    current = category
    while current.parent_id:
        depth += 1
        current = current.parent
    return depth


def migrate_system_categories_to_user_copies(apps, schema_editor):
    User = apps.get_model("auth", "User")
    Category = apps.get_model("expenses", "Category")
    Expense = apps.get_model("expenses", "Expense")

    system_categories = list(
        Category.objects.filter(is_system=True, user__isnull=True).select_related(
            "parent",
            "parent__parent",
            "parent__parent__parent",
            "parent__parent__parent__parent",
        )
    )
    system_categories.sort(key=_category_depth)

    if not system_categories:
        return

    Category.objects.filter(user__isnull=False, is_system=True).update(is_system=False)

    for user in User.objects.all().iterator():
        template_to_user_category = {}

        for template in system_categories:
            defaults = {
                "category_type": template.category_type,
                "keywords": template.keywords,
                "is_system": False,
            }
            parent = template_to_user_category.get(template.parent_id)
            if parent:
                defaults["parent_id"] = parent.pk

            user_category, created = Category.objects.get_or_create(
                user_id=user.pk,
                name=template.name,
                defaults=defaults,
            )

            if not created and user_category.is_system:
                user_category.is_system = False
                user_category.save(update_fields=["is_system"])

            template_to_user_category[template.pk] = user_category

        for template in system_categories:
            user_category = template_to_user_category[template.pk]
            Category.objects.filter(user_id=user.pk, parent_id=template.pk).update(
                parent_id=user_category.pk
            )
            Expense.objects.filter(
                user_id=user.pk,
                category_obj_id=template.pk,
            ).update(
                category_obj_id=user_category.pk,
                category=user_category.name,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("expenses", "0010_category_income_type"),
    ]

    operations = [
        migrations.RunPython(
            migrate_system_categories_to_user_copies,
            migrations.RunPython.noop,
        ),
    ]
