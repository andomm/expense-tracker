from django import forms
from django.db import models
from .models import Expense, Category, ExpenseSplitRule


UNCATEGORIZED_SENTINEL = "uncategorized"


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
        categories = Category.objects.filter(
            models.Q(is_system=True) | models.Q(user=user)
        ).order_by("name") if user else Category.objects.none()
        choices = [("", "All categories"), (UNCATEGORIZED_SENTINEL, "Uncategorized")]
        choices += [(str(c.pk), c.name) for c in categories]
        self.fields["category_filter"].choices = choices


class ExpenseForm(forms.ModelForm):
    category_obj = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        required=False,
        label="Category",
        help_text="Select a category for this expense"
    )
    split_rule = forms.ModelChoiceField(
        queryset=ExpenseSplitRule.objects.all(),
        required=False,
        label="Splitting Rule",
        help_text="Optional: Select a split rule if this expense is shared"
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
            # Filter categories to show system categories + user's custom categories
            self.fields['category_obj'].queryset = Category.objects.filter(
                models.Q(is_system=True) | models.Q(user=user)
            )
            # Filter split rules to user's rules
            self.fields['split_rule'].queryset = ExpenseSplitRule.objects.filter(user=user)
    
    def save(self, commit=True):
        expense = super().save(commit=False)
        if self.cleaned_data.get('category_obj'):
            expense.category_obj = self.cleaned_data['category_obj']
            expense.category = self.cleaned_data['category_obj'].name
        if commit:
            expense.save()
        return expense


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "category_type", "keywords"]
        help_text = "Create a new custom category"
        widgets = {
            "keywords": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "Comma-separated keywords for automatic matching (e.g., lidl,prisma,market)"
            }),
        }



class CSVUploadForm(forms.Form):
    file = forms.FileField(label="Select a CSV file")
