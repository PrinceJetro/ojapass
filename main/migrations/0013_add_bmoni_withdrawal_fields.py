# Generated migration to add BMONI wallet/withdrawal fields
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('main', '0012_ojauser_bmoni_sync_attempts_ojauser_bmoni_sync_error_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='ojauser',
            name='smart_wallet_id',
            field=models.CharField(max_length=255, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='ojauser',
            name='bmoni_withdrawal_account_id',
            field=models.CharField(max_length=255, null=True, blank=True),
        ),
    ]
