from typing import Self
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models

MAX_CATEGORY_DEPTH = 5


class Category(models.Model):
    CATEGORY_TYPE_EXPENSE = "expense"
    CATEGORY_TYPE_SAVING = "saving"
    CATEGORY_TYPE_TRANSFER = "transfer"
    CATEGORY_TYPE_CHOICES = [
        (CATEGORY_TYPE_EXPENSE, "Expense"),
        (CATEGORY_TYPE_SAVING, "Saving"),
        (CATEGORY_TYPE_TRANSFER, "Transfer"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=100)
    category_type = models.CharField(
        max_length=20, choices=CATEGORY_TYPE_CHOICES, default=CATEGORY_TYPE_EXPENSE
    )
    is_system = models.BooleanField(default=False)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subcategories",
    )
    keywords = models.TextField(
        blank=True,
        help_text="Comma-separated keywords for auto-matching expenses (e.g., 'lidl,prisma,k-market')",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "name")
        verbose_name_plural = "Categories"

    def __str__(self) -> str:
        return str(self.name)

    def get_depth(self) -> int:
        """Return the depth of this category (root = 1, max = MAX_CATEGORY_DEPTH)."""
        depth = 1
        current = self
        while current.parent_id:
            depth += 1
            current = current.parent
        return depth

    def get_root(self) -> Self:
        """Return the top-level ancestor (or self if already root)."""
        current = self
        while current.parent_id:
            current = current.parent
        return current

    def get_all_descendant_ids(self) -> list[int]:
        """Return PKs of all descendants via breadth-first traversal."""
        ids: list[int] = []
        queue = list(self.subcategories.values_list("pk", flat=True))
        while queue:
            ids.extend(queue)
            queue = list(
                Category.objects.filter(parent_id__in=queue).values_list("pk", flat=True)
            )
        return ids

    def clean(self):
        super().clean()
        if not self.parent:
            return

        if self.parent_id == self.pk:
            raise ValidationError({"parent": "A category cannot be its own parent."})

        parent_depth = self.parent.get_depth()
        if parent_depth >= MAX_CATEGORY_DEPTH:
            raise ValidationError(
                {
                    "parent": (
                        f"Maximum category depth is {MAX_CATEGORY_DEPTH}. "
                        f"The selected parent is already at depth {parent_depth}."
                    )
                }
            )

        if self.category_type != self.parent.category_type:
            raise ValidationError(
                {"category_type": "Subcategory type must match the parent category type."}
            )

        if self.is_system and not self.parent.is_system:
            raise ValidationError(
                {"parent": "System categories can only use other system categories as parents."}
            )

        if (
            not self.is_system
            and self.parent.user_id is not None
            and self.parent.user_id != self.user_id
        ):
            raise ValidationError(
                {"parent": "Parent category must be yours or a system category."}
            )

    def get_keywords_list(self) -> list[str]:
        """Return keywords as a list of lowercase strings."""
        if not self.keywords:
            return []
        return [kw.strip().lower() for kw in str(self.keywords).split(",")]

    def get_all_keywords_list(self) -> list[str]:
        """Return own keywords plus all descendant keywords without duplicates (breadth-first)."""
        keywords: list[str] = []
        seen: set[str] = set()
        queue: list[Category] = [self]
        while queue:
            current = queue.pop(0)
            for keyword in current.get_keywords_list():
                if keyword and keyword not in seen:
                    seen.add(keyword)
                    keywords.append(keyword)
            queue.extend(current.subcategories.all())
        return keywords

    def get_all_keywords(self) -> str:
        return ",".join(self.get_all_keywords_list())


class ExpenseSplitRule(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    split_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "name")

    def __str__(self):
        return f"{self.name} ({self.split_percentage}%)"


class Expense(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    category = models.CharField(
        max_length=100
    )  # Keep as CharField for backwards compat
    category_obj = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True
    )
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    user_share = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    split_rule = models.ForeignKey(
        ExpenseSplitRule, on_delete=models.SET_NULL, null=True, blank=True
    )
    receiver = models.CharField(max_length=100, blank=True)

    def save(self, *args, **kwargs):
        # Auto-calculate user_share if split rule is set
        if self.split_rule:
            self.user_share = self.amount * (self.split_rule.split_percentage / 100)
        elif self.user_share is None:
            # Default to full amount if no split rule
            self.user_share = self.amount
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.date} - {self.description or 'No description'} - €{self.amount}"
