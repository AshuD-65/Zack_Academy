from django.db import migrations, models
import django.core.validators
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0008_remove_payment_system'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='price',
            field=models.DecimalField(decimal_places=2, default=Decimal('2.00'), max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal('0.50'))]),
        ),
    ]


