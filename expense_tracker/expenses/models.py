from django.db import models
from django.contrib.auth.models import User

# Create your models here.


class Category(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=100)
    is_system = models.BooleanField(default=False)
    keywords = models.TextField(blank=True, help_text="Comma-separated keywords for auto-matching expenses (e.g., 'lidl,prisma,k-market')")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'name')
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name
    
    def get_keywords_list(self):
        """Return keywords as a list of lowercase strings."""
        if not self.keywords:
            return []
        return [kw.strip().lower() for kw in self.keywords.split(',')]


class ExpenseSplitRule(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    split_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'name')

    def __str__(self):
        return f"{self.name} ({self.split_percentage}%)"


class Expense(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    category = models.CharField(max_length=100)  # Keep as CharField for backwards compat
    category_obj = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    user_share = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    split_rule = models.ForeignKey(ExpenseSplitRule, on_delete=models.SET_NULL, null=True, blank=True)
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
