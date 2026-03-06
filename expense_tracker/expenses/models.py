from django.db import models
from django.contrib.auth.models import User

# Create your models here.


class Expense(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    category = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    receiver = models.CharField(max_length=100, blank=True)
