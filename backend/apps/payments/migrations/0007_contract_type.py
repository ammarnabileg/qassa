from django.db import migrations


def seed(apps, schema_editor):
    T = apps.get_model("payments", "KycDocumentType")
    T.objects.get_or_create(code="signed_contract", defaults=dict(
        stage="contract", name_ar="عقد KlickPay موقّع", name_en="Signed KlickPay contract",
        help_ar="نزّل العقد، وقّعه واختمه، وارفعه هنا", help_en="Download the contract, sign and stamp it, upload it here",
        required=True, sort=100))


class Migration(migrations.Migration):
    dependencies = [("payments", "0006_gatewayaccount_contract_file_and_more")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
