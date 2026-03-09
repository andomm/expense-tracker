from dataclasses import dataclass

from django.contrib.auth.models import User
from django.db.models import Q

from expenses.models import Category


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


def _category_depth(category: Category) -> int:
    """Compute depth by walking the already-loaded parent chain."""
    depth = 1
    current = category
    while current.parent_id:
        depth += 1
        current = current.parent
    return depth


def categorize_expense(
    text: str,
    user: User,
) -> tuple[Category | None, str | None]:
    """
    Match an expense text to a category using keyword matching.
    More specific (deeper) categories take priority over general ones.

    Returns:
        (category_obj, matched_keyword) if match found
        (None, None) if no match
    """
    if not text or not text.strip():
        return None, None

    text_lower = text.lower()

    # Load up to 5 levels of parent chain in one query
    categories = list(
        Category.objects.filter(Q(is_system=True) | Q(user=user))
        .exclude(keywords="")
        .select_related(
            "parent",
            "parent__parent",
            "parent__parent__parent",
            "parent__parent__parent__parent",
        )
    )

    # Sort deepest-first so more specific categories are checked first
    categories.sort(key=_category_depth, reverse=True)

    for category in categories:
        for keyword in category.get_keywords_list():
            if keyword in text_lower:
                return category, keyword

    return None, None
