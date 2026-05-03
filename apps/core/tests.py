import pytest
from django.urls import reverse
from apps.core.models import Account, AccountType

@pytest.mark.django_db
def test_account_creation():
    account = Account.objects.create(
        code='1001',
        name='Test Asset',
        account_type=AccountType.ASSET,
        is_leaf=True
    )
    assert account.code == '1001'
    assert Account.objects.count() == 1

@pytest.mark.django_db
def test_dashboard_view(admin_client):
    url = reverse('core:dashboard')
    response = admin_client.get(url)
    assert response.status_code == 200
