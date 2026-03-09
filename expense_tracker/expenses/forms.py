from django import forms
from django.db import models

from .models import Expense, Category, ExpenseSplitRule, MAX_CATEGORY_DEPTH


UNCATEGORIZED_SENTINEL = "uncategorized"


def get_user_category_queryset(user):
    if not user or not user.is_authenticated:
        return Category.objects.none()

    return Category.objects.filter(
        models.Q(is_system=True) | models.Q(user=user)
    ).select_related(
        "parent",
        "parent__parent",
        "parent__parent__parent",
        "parent__parent__parent__parent",
    )


def _flatten_category_tree(
    categories: list,
    *,
    exclude_id: int | None = None,
    exclude_descendant_ids: set[int] | None = None,
) -> list[tuple]:
    """
    Return a flat list of (category, depth) pairs ordered so each parent
    is immediately followed by all its children (recursively), alphabetically
    within each level. Optionally exclude a category and its descendants.
    """
    by_parent: dict[int | None, list] = {}
    for cat in categories:
        pid = cat.parent_id
        by_parent.setdefault(pid, []).append(cat)

    for children in by_parent.values():
        children.sort(key=lambda c: c.name.lower())

    excluded = set()
    if exclude_id is not None:
        excluded.add(exclude_id)
    if exclude_descendant_ids:
        excluded.update(exclude_descendant_ids)

    result: list[tuple] = []

    def traverse(parent_id, depth):
        for cat in by_parent.get(parent_id, []):
            if cat.pk in excluded:
                continue
            result.append((cat, depth))
            traverse(cat.pk, depth + 1)

    traverse(None, 1)
    return result


def build_category_choices(
    categories,
    *,
    empty_label=None,
    include_uncategorized=False,
    exclude_id: int | None = None,
    exclude_descendant_ids: set[int] | None = None,
):
    """Build a flat choice list with dash-prefixed labels showing depth."""
    flat = _flatten_category_tree(
        categories,
        exclude_id=exclude_id,
        exclude_descendant_ids=exclude_descendant_ids,
    )

    choices = []
    if empty_label is not None:
        choices.append(("", empty_label))
    if include_uncategorized:
        choices.append((UNCATEGORIZED_SENTINEL, "Uncategorized"))

    for cat, depth in flat:
        prefix = "— " * (depth - 1)
        choices.append((str(cat.pk), f"{prefix}{cat.name}"))

    return choices


class SortForm(forms.Form):
    ORDER_CHOICES = [
        ("-date", "Date — newest first"),
        ("date", "Date — oldest first"),
        ("-amount", "Amount — highest first"),
        ("amount", "Amount — lowest first"),
    ]
    order_by = forms.ChoiceField(
        choices=ORDER_CHOICES,
        required=False,
        label="Sort by",
    )
    category_filter = forms.ChoiceField(
        choices=[],
        required=False,
        label="Filter by category",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        categories = list(get_user_category_queryset(user))
        self.fields["category_filter"].choices = build_category_choices(
            categories,
            empty_label="All categories",
            include_uncategorized=True,
        )


class ExpenseForm(forms.ModelForm):
    category_obj = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        required=False,
        label="Category",
        help_text="Select a category for this expense",
    )
    split_rule = forms.ModelChoiceField(
        queryset=ExpenseSplitRule.objects.all(),
        required=False,
        label="Splitting Rule",
        help_text="Optional: Select a split rule if this expense is shared",
    )

    class Meta:
        model = Expense
        fields = ["date", "description", "amount", "split_rule", "receiver"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            categories = list(get_user_category_queryset(user))
            self.fields["category_obj"].queryset = get_user_category_queryset(user)
            self.fields["category_obj"].choices = build_category_choices(
                categories,
                empty_label="---------",
            )
            # Filter split rules to user's rules
            self.fields["split_rule"].queryset = ExpenseSplitRule.objects.filter(
                user=user
            )

    def save(self, commit=True):
        expense = super().save(commit=False)
        if self.cleaned_data.get("category_obj"):
            expense.category_obj = self.cleaned_data["category_obj"]
            expense.category = self.cleaned_data["category_obj"].name
        if commit:
            expense.save()
        return expense


class CategoryForm(forms.ModelForm):
    parent = forms.ModelChoiceField(
        queryset=Category.objects.none(),
        required=False,
        help_text="Optional: choose a parent category to create a subcategory.",
    )

    class Meta:
        model = Category
        fields = ["name", "parent", "category_type", "keywords"]
        help_text = "Create a new custom category"
        widgets = {
            "keywords": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Comma-separated keywords for automatic matching (e.g., lidl,prisma,market)",
                }
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        all_cats = list(get_user_category_queryset(user))

        # Exclude self and its descendants from parent candidates
        exclude_id = self.instance.pk if self.instance.pk else None
        descendant_ids = set(self.instance.get_all_descendant_ids()) if self.instance.pk else set()

        # Only categories that still have room for a child (depth < MAX_CATEGORY_DEPTH)
        valid_parents = [
            cat for cat in all_cats
            if cat.pk not in descendant_ids
            and (exclude_id is None or cat.pk != exclude_id)
            and cat.get_depth() < MAX_CATEGORY_DEPTH
        ]

        self.fields["parent"].queryset = Category.objects.filter(
            pk__in=[c.pk for c in valid_parents]
        )
        self.fields["parent"].choices = [("", "---------")] + [
            (str(cat.pk), label)
            for cat, label in [
                (cat, "— " * (cat.get_depth() - 1) + cat.name)
                for cat in sorted(valid_parents, key=lambda c: c.name.lower())
            ]
        ]

    def clean_parent(self):
        parent = self.cleaned_data.get("parent")
        if parent and parent.get_depth() >= MAX_CATEGORY_DEPTH:
            raise forms.ValidationError(
                f"The selected parent is at the maximum allowed depth ({MAX_CATEGORY_DEPTH}). "
                "Choose a shallower category."
            )
        return parent


class CSVUploadForm(forms.Form):
    IMPORT_FORMAT_FINNISH_BANK = "osuuspankki_csv"
    IMPORT_FORMAT_CHOICES = [
        (IMPORT_FORMAT_FINNISH_BANK, "OP"),
    ]

    file = forms.FileField(label="Select a CSV file")
    import_format = forms.ChoiceField(
        choices=IMPORT_FORMAT_CHOICES,
        label="File format",
        initial=IMPORT_FORMAT_FINNISH_BANK,
    )
