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

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        categories = list(get_user_category_queryset(user))
        self.fields["category_filter"].choices = build_category_choices(
            categories,
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
        # category_obj is not in Meta.fields so Django won't populate it from the
        # instance automatically — set it explicitly when editing an existing expense.
        if self.instance and self.instance.pk and self.instance.category_obj_id:
            self.initial["category_obj"] = self.instance.category_obj_id

    def save(self, commit=True):
        expense = super().save(commit=False)
        if self.cleaned_data.get("category_obj"):
            expense.category_obj = self.cleaned_data["category_obj"]
            expense.category = self.cleaned_data["category_obj"].name
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

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        categories = list(get_user_category_queryset(user))
        self.fields["category_obj"].queryset = get_user_category_queryset(user)
        self.fields["category_obj"].choices = build_category_choices(categories)


class BaseSplitRowFormSet(BaseFormSet):
    def __init__(self, *args, total_amount=None, **kwargs):
        self.total_amount = abs(total_amount) if total_amount is not None else None
        super().__init__(*args, **kwargs)

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        if self.total_amount is None:
            return

        split_total = Decimal("0")
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            amount = form.cleaned_data.get("amount")
            if amount:
                split_total += amount

        if split_total > self.total_amount:
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

    def clean_keywords(self):
        keywords_raw = self.cleaned_data.get("keywords", "")
        if not keywords_raw or not keywords_raw.strip():
            return keywords_raw

        submitted_keywords = [
            kw.strip().lower() for kw in keywords_raw.split(",") if kw.strip()
        ]

        if not submitted_keywords:
            return keywords_raw

        user = self.instance.user if self.instance else None
        if not user:
            return keywords_raw

        # Get all categories for this user, excluding self and own descendants
        exclude_ids = set()
        if self.instance.pk:
            exclude_ids.add(self.instance.pk)
            exclude_ids.update(self.instance.get_all_descendant_ids())

        other_categories = Category.objects.filter(user=user).exclude(
            pk__in=exclude_ids
        ).select_related(
            "parent",
            "parent__parent",
            "parent__parent__parent",
            "parent__parent__parent__parent",
        )

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
