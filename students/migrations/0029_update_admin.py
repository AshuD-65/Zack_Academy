# Generated migration to update admin credentials
from django.db import migrations
from django.contrib.auth.hashers import make_password

def update_admin_credentials(apps, schema_editor):
    """
    Update admin credentials on production database.
    Change the values below to your desired credentials.
    """
    User = apps.get_model('auth', 'User')
    
    # Admin credentials - will be applied on next deployment
    NEW_USERNAME = 'zack_admin'
    NEW_EMAIL = 'admin@zackacademy.com'
    NEW_PASSWORD = 'Zack@2024Admin'
    
    try:
        # Find the first superuser
        admin = User.objects.filter(is_superuser=True).first()
        
        if admin:
            admin.username = NEW_USERNAME
            admin.email = NEW_EMAIL
            admin.password = make_password(NEW_PASSWORD)
            admin.save()
            print(f"✅ Admin credentials updated successfully!")
            print(f"   Username: {NEW_USERNAME}")
            print(f"   Email: {NEW_EMAIL}")
        else:
            # Create admin if none exists
            User.objects.create_superuser(
                username=NEW_USERNAME,
                email=NEW_EMAIL,
                password=NEW_PASSWORD
            )
            print(f"✅ New admin created!")
    except Exception as e:
        print(f"❌ Error updating admin: {e}")

class Migration(migrations.Migration):

    dependencies = [
        ('students', '0028_course_main_file_alter_exam_num_questions'),
    ]

    operations = [
        migrations.RunPython(update_admin_credentials),
    ]
