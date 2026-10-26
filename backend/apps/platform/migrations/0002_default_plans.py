"""Plans from the approved design (reference pricing page). Prices are editable by the platform owner.
Existing tenants are placed on 'pro' (3 branches), which fits every tenant created before plans existed."""
import datetime

from django.db import migrations

PLANS = [("basic", "أساسي", "Basic", "15.000", 1, 3, 1), ("pro", "احترافي", "Pro", "29.000", 3, 10, 2),
         ("chains", "سلاسل", "Chains", "69.000", 99, 99, 3)]


def forwards(apps, schema_editor):
    Plan, Subscription, Tenant = (apps.get_model("platform", "Plan"), apps.get_model("platform", "Subscription"),
                                  apps.get_model("tenancy", "Tenant"))
    for code, ar, en, price, br, st, sort in PLANS:
        Plan.objects.get_or_create(code=code, defaults=dict(name_ar=ar, name_en=en, monthly_price=price,
                                                            max_branches=br, max_staff=st, sort=sort))
    pro = Plan.objects.get(code="pro")
    today = datetime.date.today()
    for t in Tenant.objects.filter(subscription__isnull=True):
        Subscription.objects.create(tenant=t, plan=pro, started_on=today, current_period_end=today + datetime.timedelta(days=30))


class Migration(migrations.Migration):
    dependencies = [("platform", "0001_initial"), ("tenancy", "0003_sync_role_permissions")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
