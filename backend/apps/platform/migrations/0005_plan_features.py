from django.db import migrations

FEATURES = {
    "basic": (["كاشير وفواتير", "حجوزات وطابور", "تقارير أساسية", "دعم بالواتساب"],
              ["POS and invoices", "Bookings and queue", "Basic reports", "WhatsApp support"], False),
    "pro": (["كل مميزات الأساسي", "كوبونات وعروض", "نقاط وولاء", "مخزون ومشتريات", "رسائل واتساب تلقائية"],
            ["Everything in Basic", "Coupons and offers", "Loyalty points", "Stock and purchasing", "Automatic WhatsApp messages"], True),
    "chains": (["كل مميزات الاحترافي", "فروع بلا حدود", "لوحة موحدة للفروع", "دومين خاص لتطبيق العملاء", "مدير حساب مخصص"],
               ["Everything in Pro", "Unlimited branches", "One dashboard for all branches", "Custom domain for the customer app", "Dedicated account manager"], False),
}


def seed(apps, schema_editor):
    Plan = apps.get_model("platform", "Plan")
    for code, (ar, en, hl) in FEATURES.items():
        Plan.objects.filter(code=code, features_ar=[]).update(features_ar=ar, features_en=en, highlight=hl)


class Migration(migrations.Migration):
    dependencies = [("platform", "0004_billing_support_leads")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
