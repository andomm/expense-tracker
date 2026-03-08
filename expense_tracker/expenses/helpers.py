from django.contrib.auth.models import User
from django.db.models import Q

from expenses.models import Category
from dataclasses import dataclass


@dataclass(frozen=True)
class CategorizationMatch:
    category: Category | None
    keyword: str | None
    source: str | None


def categorize_from_sources(
    *sources: tuple[str, str],
    user: User,
) -> CategorizationMatch:
    for source_name, source_value in sources:
        category_obj, matched_keyword = categorize_expense(source_value, user)
        if category_obj:
            return CategorizationMatch(
                category=category_obj,
                keyword=matched_keyword,
                source=source_name,
            )
    return CategorizationMatch(category=None, keyword=None, source=None)


def categorize_expense(
    text: str,
    user: User,
) -> tuple[Category | None, str | None]:
    """
    Match an expense text to a category using keyword matching.

    Returns:
        (category_obj, matched_keyword) if match found
        (None, None) if no match
    """
    if not text or not text.strip():
        return None, None

    text_lower = text.lower()

    # Get all categories (system + user's custom)
    categories = Category.objects.filter(Q(is_system=True) | Q(user=user)).exclude(
        keywords=""
    )

    # Try to find a matching category
    for category in categories:
        keywords = category.get_keywords_list()
        for keyword in keywords:
            if keyword in text_lower:
                return category, keyword

    return None, None
