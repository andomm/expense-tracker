from collections import defaultdict
from decimal import Decimal

from django import forms
from django.forms import BaseFormSet, formset_factory
from django.db import models

from .models import (
    Expense,
    Category,
    ExpenseSplitRule,
    MAX_CATEGORY_DEPTH,
)


UNCATEGORIZED_SENTINEL = "uncategorized"


def get_user_category_queryset(user):
    if not user or not user.is_authenticated:
        return Category.objects.none()

    return Category.objects.filter(user=user).select_related(
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
    category_filter = forms.ChoiceField(
        choices=[],
        required=False,
        label="Filter by category",
    )
    search = forms.CharField(
        required=False,
        label="Search",
        max_length=100,
    )

    def __init__(self, data=None, *args, user=None, **kwargs):
        if data is not None and data.get("category_filter") == "all":
            data = data.copy()
            data["category_filter"] = ""
        super().__init__(data, *args, **kwargs)
        self.categories = list(get_user_category_queryset(user))
        self.fields["category_filter"].choices = build_category_choices(
            self.categories,
            empty_label="All categories",
            include_uncategorized=True,
        )
        self.fields["search"].widget.attrs.update(
            {
                "placeholder": "Search receiver, description, or category",
                "class": "rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900",
            }
        )


class ExpenseForm(forms.ModelForm):
    category_obj = forms.ModelChoiceField(
        queryset=Category.objects.none(),
        required=False,
        label="Category",
        help_text="Select a category for this expense",
    )
    split_rule = forms.ModelChoiceField(
        queryset=ExpenseSplitRule.objects.none(),
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

    def __init__(self, *args, user=None, show_choices=True, **kwargs):
        super().__init__(*args, **kwargs)
        categories = get_user_category_queryset(user)
        self.fields["category_obj"].queryset = categories
        if show_choices:
            self.fields["category_obj"].choices = build_category_choices(
                categories, empty_label="---------"
            )
        if user and user.is_authenticated:
            self.fields["split_rule"].queryset = ExpenseSplitRule.objects.filter(user=user)
        # category_obj is not in Meta.fields so Django won't populate it from the
        # instance automatically — set it explicitly when editing an existing expense.
        if self.instance and self.instance.pk and self.instance.category_obj_id:
            self.initial["category_obj"] = self.instance.category_obj_id

    def save(self, commit=True, *, clear_category=False):
        expense = super().save(commit=False)
        category = self.cleaned_data["category_obj"]
        if category or clear_category:
            expense.category_obj = category
            expense.category = category.name if category else ""
        if commit:
            expense.save()
        return expense


class BulkCategoryUpdateForm(forms.Form):
    expense_ids = forms.ModelMultipleChoiceField(
        queryset=Expense.objects.none(),
        required=True,
        widget=forms.MultipleHiddenInput,
        error_messages={"required": "Select at least one expense to update."},
    )
    category_obj = forms.ModelChoiceField(
        queryset=Category.objects.none(),
        required=True,
        label="Change selected to",
        error_messages={"required": "Select a category."},
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["expense_ids"].queryset = (
            Expense.objects.filter(user=user)
            if user and user.is_authenticated
            else Expense.objects.none()
        )

        categories = list(get_user_category_queryset(user))
        self.fields["category_obj"].queryset = get_user_category_queryset(user)
        self.fields["category_obj"].choices = build_category_choices(categories)
        self.fields["category_obj"].widget.attrs.update(
            {
                "class": "rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900",
            }
        )


class SplitRowForm(forms.Form):
    category_obj = forms.ModelChoiceField(
        queryset=Category.objects.none(),
        label="Split category",
    )
    amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Split amount",
    )

    def __init__(self, *args, user=None, show_choices=True, **kwargs):
        super().__init__(*args, **kwargs)
        categories = get_user_category_queryset(user)
        self.fields["category_obj"].queryset = categories
        if show_choices:
            self.fields["category_obj"].choices = build_category_choices(categories)


class BaseSplitRowFormSet(BaseFormSet):
    def __init__(self, *args, total_amount=None, **kwargs):
        self.total_amount = abs(total_amount) if total_amount is not None else None
        super().__init__(*args, **kwargs)

    @property
    def parts(self) -> list[tuple[Decimal, Category]]:
        return [
            (data["amount"], data["category_obj"])
            for form in self.forms
            if (data := form.cleaned_data)
            and not data.get("DELETE")
            and data.get("amount") is not None
            and data.get("category_obj") is not None
        ]

    @property
    def split_total(self) -> Decimal:
        return sum((amount for amount, _ in self.parts), Decimal(0))

    def clean(self):
        super().clean()
        if any(self.errors) or self.total_amount is None:
            return
        if self.split_total > self.total_amount:
            raise forms.ValidationError(
                "Split amounts cannot exceed the expense amount."
            )


SplitRowFormSet = formset_factory(
    SplitRowForm,
    formset=BaseSplitRowFormSet,
    extra=0,
    can_delete=True,
)


class CategoryForm(forms.ModelForm):
    parent = forms.ModelChoiceField(
        queryset=Category.objects.none(),
        required=False,
        help_text="Optional: choose a parent category to create a subcategory.",
    )

    class Meta:
        model = Category
        fields = ["name", "parent", "category_type", "keywords"]
        help_text = "Create a category"
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

        owned = (
            Category.objects.filter(user=user)
            if user and user.is_authenticated
            else Category.objects.none()
        )
        all_categories = list(owned)
        children: dict[int | None, list[Category]] = defaultdict(list)
        for category in all_categories:
            children[category.parent_id].append(category)

        pk = self.instance.pk
        direct_children = children[pk] if pk is not None else []
        self.child_types = {child.category_type for child in direct_children}
        self.subtree_ids = {pk} if pk is not None else set()
        height = 1
        stack = [(child, 2) for child in direct_children]
        while stack:
            child, level = stack.pop()
            if child.pk in self.subtree_ids:
                continue
            self.subtree_ids.add(child.pk)
            height = max(height, level)
            stack.extend((node, level + 1) for node in children[child.pk])

        parents = [
            (cat, depth)
            for cat, depth in _flatten_category_tree(all_categories)
            if cat.pk not in self.subtree_ids and depth + height <= MAX_CATEGORY_DEPTH
        ]
        parent_field = self.fields["parent"]
        parent_field.queryset = owned.filter(pk__in=[cat.pk for cat, _ in parents])
        parent_field.choices = [("", "---------")] + [
            (str(cat.pk), "— " * (depth - 1) + cat.name) for cat, depth in parents
        ]

    def clean_name(self) -> str:
        name = self.cleaned_data["name"]
        if Category.objects.filter(user_id=self.instance.user_id, name=name).exclude(
            pk=self.instance.pk
        ).exists():
            raise forms.ValidationError("You already have a category with this name.")
        return name

    def clean_category_type(self) -> str:
        category_type = self.cleaned_data["category_type"]
        if self.child_types - {category_type}:
            raise forms.ValidationError("Category type must match its subcategories.")
        return category_type

    def clean_keywords(self) -> str:
        keywords_raw = self.cleaned_data.get("keywords", "")
        if not keywords_raw or not keywords_raw.strip():
            return keywords_raw

        submitted_keywords = [
            kw.strip().lower() for kw in keywords_raw.split(",") if kw.strip()
        ]

        if not submitted_keywords:
            return keywords_raw

        if not self.instance.user_id:
            return keywords_raw

        # A parent can keep keywords also used by its own descendants.
        other_categories = Category.objects.filter(user_id=self.instance.user_id).exclude(
            pk__in=self.subtree_ids
        ).only("name", "keywords").order_by("pk")

        # Build keyword → category name mapping from all other categories
        keyword_to_category: dict[str, str] = {}
        for cat in other_categories:
            for kw in cat.get_keywords_list():
                if kw not in keyword_to_category:
                    keyword_to_category[kw] = cat.name

        # Check for conflicts
        conflicts = []
        for kw in submitted_keywords:
            if kw in keyword_to_category:
                conflicts.append(
                    f"Keyword '{kw}' is already used by category '{keyword_to_category[kw]}'."
                )

        if conflicts:
            raise forms.ValidationError(" ".join(conflicts))

        return keywords_raw


class CSVUploadForm(forms.Form):
    IMPORT_FORMAT_FINNISH_BANK = "osuuspankki_csv"
    IMPORT_FORMAT_SPIIR = "spiir_csv"
    IMPORT_FORMAT_CHOICES = [
        (IMPORT_FORMAT_FINNISH_BANK, "OP"),
        (IMPORT_FORMAT_SPIIR, "Spiir"),
    ]

    file = forms.FileField(label="Select a CSV file")
    import_format = forms.ChoiceField(
        choices=IMPORT_FORMAT_CHOICES,
        label="File format",
        initial=IMPORT_FORMAT_FINNISH_BANK,
    )
