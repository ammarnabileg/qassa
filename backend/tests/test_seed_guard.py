import pytest
from django.core.management import CommandError, call_command

pytestmark = pytest.mark.django_db


def test_seed_refuses_production(settings):
    settings.ENVIRONMENT = "production"
    with pytest.raises(CommandError):
        call_command("seed_dev")


def test_seed_on_staging_requires_explicit_password(settings, monkeypatch):
    settings.ENVIRONMENT = "staging"
    monkeypatch.delenv("SEED_PASSWORD", raising=False)
    with pytest.raises(CommandError, match="SEED_PASSWORD"):
        call_command("seed_dev")
