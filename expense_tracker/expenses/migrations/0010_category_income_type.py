from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('expenses', '0009_category_parent'),
    ]

    operations = [
        migrations.AlterField(
            model_name='category',
            name='category_type',
            field=models.CharField(
                choices=[
                    ('expense', 'Expense'),
                    ('saving', 'Saving'),
                    ('transfer', 'Transfer'),
                    ('income', 'Income'),
                ],
                default='expense',
                max_length=20,
            ),
        ),
    ]
