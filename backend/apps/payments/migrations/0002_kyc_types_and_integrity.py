from django.db import migrations

from apps.core.db import composite_tenant_fk

# A starting list only — KlickPay's actual requirements must be confirmed; the platform team edits it.
DEFAULT_TYPES = [
    ("commercial_license", "الرخصة التجارية", "Commercial license", "سارية، وباسم الشركة", "Valid, in the company's name"),
    ("commercial_registration", "شهادة السجل التجاري أو عقد التأسيس", "Commercial registration / articles", "", ""),
    ("owner_civil_id", "البطاقة المدنية للمالك (وجهين)", "Owner's civil ID (both sides)", "", ""),
    ("signatory", "اعتماد التوقيع للمفوَّض", "Authorised signatory", "لو المفوَّض غير المالك", "If the signatory is not the owner"),
    ("iban_certificate", "شهادة IBAN من البنك باسم الشركة", "Bank IBAN certificate in the company's name", "", ""),
]


def seed(apps, schema_editor):
    T = apps.get_model("payments", "KycDocumentType")
    for i, (code, ar, en, har, hen) in enumerate(DEFAULT_TYPES):
        T.objects.get_or_create(code=code, defaults=dict(name_ar=ar, name_en=en, help_ar=har, help_en=hen, sort=i,
                                                         required=code != "signatory"))


class Migration(migrations.Migration):
    dependencies = [("payments", "0001_initial"), ("pos", "0006_alter_payment_method")]
    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
        composite_tenant_fk("payments_onlinepayment", "invoice_id", "pos_invoice"),
        composite_tenant_fk("payments_onlinepayment", "payment_id", "pos_payment"),
    ]
