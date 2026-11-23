from collections import defaultdict, deque
from collections.abc import Iterator

from django.contrib.auth.models import User

from .models import Category


def category_groups(user: User) -> list[dict]:
    """Tree rows and keyword counts for categories owned by this user."""
    by_parent: dict[int | None, list[Category]] = defaultdict(list)
    for category in Category.objects.filter(user=user):
        by_parent[category.parent_id].append(category)
    for siblings in by_parent.values():
        siblings.sort(key=lambda category: (category.name.lower(), category.pk))

    def descendants(parent: Category) -> Iterator[dict]:
        for child in by_parent[parent.pk]:
            yield {"category": child, "keyword_count": len(child.get_keywords_list())}
            yield from descendants(child)

    groups = []
    for root in by_parent[None]:
        # Count each non-empty keyword in the root and its descendants once.
        keywords: set[str] = set()
        queue = deque([root])
        while queue:
            category = queue.popleft()
            keywords.update(filter(None, category.get_keywords_list()))
            queue.extend(by_parent[category.pk])
        groups.append({
            "parent": root,
            "parent_keyword_count": len(keywords),
            "children": list(descendants(root)),
        })
    return groups
