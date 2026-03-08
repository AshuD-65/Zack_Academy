from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0009_course_price'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='duration_weeks',
            field=models.PositiveIntegerField(default=12),
        ),
    ]


