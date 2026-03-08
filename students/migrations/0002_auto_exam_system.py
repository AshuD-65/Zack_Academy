# Generated migration for automated exam system

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0001_initial'),  # Adjust this to your last migration
    ]

    operations = [
        # Add new fields to Exam model
        migrations.AddField(
            model_name='exam',
            name='is_released',
            field=models.BooleanField(default=False, help_text='Students can take exam when released'),
        ),
        migrations.AddField(
            model_name='exam',
            name='num_questions',
            field=models.PositiveIntegerField(default=10, help_text='Number of questions to generate'),
        ),
        migrations.AddField(
            model_name='exam',
            name='time_limit_minutes',
            field=models.PositiveIntegerField(default=60, help_text='Time limit in minutes'),
        ),
        
        # Add new field to ExamQuestion model
        migrations.AddField(
            model_name='examquestion',
            name='source_material',
            field=models.ForeignKey(
                blank=True,
                help_text='Material this question was generated from',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='students.coursematerial'
            ),
        ),
        
        # Remove SHORT_ANSWER from question type choices (auto-grading only supports MC and T/F)
        migrations.AlterField(
            model_name='examquestion',
            name='question_type',
            field=models.CharField(
                choices=[
                    ('MULTIPLE_CHOICE', 'Multiple Choice'),
                    ('TRUE_FALSE', 'True/False')
                ],
                default='MULTIPLE_CHOICE',
                max_length=20
            ),
        ),
        
        # Update ExamQuestion help texts
        migrations.AlterField(
            model_name='examquestion',
            name='options_json',
            field=models.JSONField(
                blank=True,
                help_text='["Option A", "Option B", "Option C", "Option D"]',
                null=True
            ),
        ),
        migrations.AlterField(
            model_name='examquestion',
            name='correct_answer',
            field=models.CharField(
                help_text='Correct answer (A, B, C, D or True/False)',
                max_length=500
            ),
        ),
        
        # Add time_taken_seconds to ExamAttempt
        migrations.AddField(
            model_name='examattempt',
            name='time_taken_seconds',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Time taken to complete',
                null=True
            ),
        ),
    ]
