from django import forms
from .models import Expense


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


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ["date", "category", "description", "amount"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
        }


class CSVUploadForm(forms.Form):
    file = forms.FileField(label="Select a CSV file")
