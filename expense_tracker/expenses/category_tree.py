from collections import defaultdict, deque
from collections.abc import Iterator

from django.contrib.auth.models import User

from .models import Category


def category_groups(user: User) -> list[dict]:
    """Legacy tree rows and counts, using only categories owned by this user."""
    by_parent: dict[int | None, list[Category]] = defaultdict(list)
    for category in Category.objects.filter(user=user):
        by_parent[category.parent_id].append(category)
    for siblings in by_parent.values():
        siblings.sort(key=lambda category: (category.name.lower(), category.pk))

    def descendants(parent: Category, depth: int) -> Iterator[dict]:
        for child in by_parent[parent.pk]:
            keywords = child.get_keywords_list()
            yield {
                "category": child,
                "depth": depth,
                "keyword_count": len(keywords),
                "keywords_full": ", ".join(keywords),
            }
            yield from descendants(child, depth + 1)

    groups = []
    for root in by_parent[None]:
        # Preserve the unique, non-empty root total and breadth-first tooltip.
        keywords: dict[str, None] = {}
        queue = deque([root])
        while queue:
            category = queue.popleft()
            keywords.update(dict.fromkeys(filter(None, category.get_keywords_list())))
            queue.extend(by_parent[category.pk])
        groups.append({
            "parent": root,
            "parent_keyword_count": len(keywords),
            "parent_keywords_full": ", ".join(keywords),
            "children": list(descendants(root, 2)),
        })
    return groups
