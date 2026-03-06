from django.contrib import admin

from .models import Expense

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'category', 'amount')
    list_filter = ('category', 'date')
    search_fields = ('description', 'category', 'user__username')
