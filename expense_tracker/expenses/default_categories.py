from django.contrib.auth.models import User

from expenses.models import Category


def _category_depth(category: Category) -> int:
    depth = 1
    current = category
    while current.parent_id:
        depth += 1
        current = current.parent
    return depth


def get_default_category_templates() -> list[Category]:
    templates = list(
        Category.objects.filter(is_system=True, user__isnull=True).select_related(
            "parent",
            "parent__parent",
            "parent__parent__parent",
            "parent__parent__parent__parent",
        )
    )
    templates.sort(key=_category_depth)
    return templates


def seed_user_default_categories(user: User) -> dict[int, Category]:
    if not user.pk:
        return {}

    seeded_categories: dict[int, Category] = {}

    for template in get_default_category_templates():
        defaults = {
            "category_type": template.category_type,
            "keywords": template.keywords,
            "is_system": False,
        }

        parent = seeded_categories.get(template.parent_id)
        if parent:
            defaults["parent"] = parent

        category, _ = Category.objects.get_or_create(
            user=user,
            name=template.name,
            defaults=defaults,
        )

        if category.is_system:
            category.is_system = False
            category.save(update_fields=["is_system"])

        seeded_categories[template.pk] = category

    return seeded_categories
