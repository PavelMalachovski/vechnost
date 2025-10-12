"""Tests for payment functionality."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

from vechnost_bot.payments.models import User, Product, Payment, Subscription, WebhookEvent
from vechnost_bot.payments.repositories import (
    UserRepository,
    ProductRepository,
    PaymentRepository,
    SubscriptionRepository,
    WebhookEventRepository,
)
from vechnost_bot.payments.services import user_has_access, apply_webhook_event
from vechnost_bot.payments.signature import compute_body_sha256, verify_tribute_signature
from vechnost_bot.payments.database import get_db, init_db, create_tables, drop_tables
from vechnost_bot.config import settings


@pytest.fixture
async def test_db():
    """Initialize test database."""
    # Use in-memory SQLite for tests
    original_db_url = settings.database_url
    settings.database_url = "sqlite+aiosqlite:///:memory:"

    init_db()
    await create_tables()

    yield

    await drop_tables()
    settings.database_url = original_db_url


@pytest.mark.asyncio
async def test_user_repository_create(test_db):
    """Test creating a user in the repository."""
    async with get_db() as session:
        user = await UserRepository.create_or_update(
            session,
            telegram_user_id=123456789,
            username="test_user",
            first_name="Test",
            last_name="User",
        )

        assert user.id is not None
        assert user.telegram_user_id == 123456789
        assert user.username == "test_user"
        assert user.first_name == "Test"
        assert user.last_name == "User"


@pytest.mark.asyncio
async def test_user_repository_update(test_db):
    """Test updating an existing user."""
    async with get_db() as session:
        # Create user
        user = await UserRepository.create_or_update(
            session,
            telegram_user_id=123456789,
            username="test_user",
        )
        user_id = user.id

        # Update user
        updated_user = await UserRepository.create_or_update(
            session,
            telegram_user_id=123456789,
            username="updated_user",
            first_name="Updated",
        )

        assert updated_user.id == user_id
        assert updated_user.username == "updated_user"
        assert updated_user.first_name == "Updated"


@pytest.mark.asyncio
async def test_product_repository_upsert(test_db):
    """Test upserting products."""
    async with get_db() as session:
        # Create product
        product = await ProductRepository.upsert(
            session,
            product_id=1,
            type="subscription",
            name="Monthly Subscription",
            amount=999,
            currency="USD",
            t_link="https://t.me/tribute/product1",
        )

        assert product.id == 1
        assert product.name == "Monthly Subscription"
        assert product.amount == 999

        # Update product
        updated_product = await ProductRepository.upsert(
            session,
            product_id=1,
            type="subscription",
            name="Updated Monthly Subscription",
            amount=1099,
            currency="USD",
        )

        assert updated_product.id == 1
        assert updated_product.name == "Updated Monthly Subscription"
        assert updated_product.amount == 1099


@pytest.mark.asyncio
async def test_payment_repository_create(test_db):
    """Test creating a payment record."""
    async with get_db() as session:
        # Create user first
        user = await UserRepository.create_or_update(
            session, telegram_user_id=123456789
        )

        # Create payment
        payment = await PaymentRepository.create(
            session,
            provider="tribute",
            event_name="payment.succeeded",
            user_id=user.id,
            telegram_user_id=123456789,
            amount=999,
            currency="USD",
            raw_body={"test": "data"},
            signature="test_signature",
            body_sha256="test_hash_123",
        )

        assert payment.id is not None
        assert payment.user_id == user.id
        assert payment.amount == 999
        assert payment.body_sha256 == "test_hash_123"


@pytest.mark.asyncio
async def test_subscription_repository_upsert(test_db):
    """Test upserting subscriptions."""
    async with get_db() as session:
        # Create user first
        user = await UserRepository.create_or_update(
            session, telegram_user_id=123456789
        )

        expires_at = datetime.utcnow() + timedelta(days=30)

        # Create subscription
        subscription = await SubscriptionRepository.upsert(
            session,
            user_id=user.id,
            subscription_id=1001,
            period="month",
            status="active",
            expires_at=expires_at,
        )

        assert subscription.id is not None
        assert subscription.subscription_id == 1001
        assert subscription.status == "active"

        # Update subscription
        updated_subscription = await SubscriptionRepository.upsert(
            session,
            user_id=user.id,
            subscription_id=1001,
            period="month",
            status="canceled",
            expires_at=expires_at,
        )

        assert updated_subscription.id == subscription.id
        assert updated_subscription.status == "canceled"


@pytest.mark.asyncio
async def test_webhook_event_repository(test_db):
    """Test webhook event repository."""
    async with get_db() as session:
        webhook = await WebhookEventRepository.create(
            session,
            name="payment.succeeded",
            sent_at=datetime.utcnow(),
            body_sha256="test_hash",
            status_code=200,
        )

        assert webhook.id is not None
        assert webhook.name == "payment.succeeded"
        assert webhook.status_code == 200


@pytest.mark.asyncio
async def test_user_has_access_no_payment(test_db):
    """Test access check for user without payment."""
    # Set payments to enabled for this test
    original_enable_payment = settings.enable_payment
    settings.enable_payment = True

    async with get_db() as session:
        # Create user without payment
        await UserRepository.create_or_update(session, telegram_user_id=123456789)

    # Check access
    has_access = await user_has_access(123456789)
    assert has_access is False

    settings.enable_payment = original_enable_payment


@pytest.mark.asyncio
async def test_user_has_access_with_subscription(test_db):
    """Test access check for user with active subscription."""
    original_enable_payment = settings.enable_payment
    settings.enable_payment = True

    async with get_db() as session:
        # Create user with active subscription
        user = await UserRepository.create_or_update(session, telegram_user_id=123456789)

        expires_at = datetime.utcnow() + timedelta(days=30)
        await SubscriptionRepository.upsert(
            session,
            user_id=user.id,
            subscription_id=1001,
            period="month",
            status="active",
            expires_at=expires_at,
        )

    # Check access
    has_access = await user_has_access(123456789)
    assert has_access is True

    settings.enable_payment = original_enable_payment


@pytest.mark.asyncio
async def test_user_has_access_payment_disabled(test_db):
    """Test access check when payments are disabled."""
    original_enable_payment = settings.enable_payment
    settings.enable_payment = False

    # Check access (should be True even without payment)
    has_access = await user_has_access(123456789)
    assert has_access is True

    settings.enable_payment = original_enable_payment


def test_compute_body_sha256():
    """Test SHA256 computation."""
    body = b'{"test": "data"}'
    hash_value = compute_body_sha256(body)

    assert isinstance(hash_value, str)
    assert len(hash_value) == 64  # SHA256 produces 64 hex chars


def test_verify_tribute_signature_valid():
    """Test signature verification with valid signature."""
    original_secret = settings.webhook_secret
    settings.webhook_secret = "test_secret"

    body = b'{"test": "data"}'
    import hmac
    import hashlib

    expected_sig = hmac.new(
        b"test_secret", body, hashlib.sha256
    ).hexdigest()

    headers = {"X-Tribute-Signature": expected_sig}

    is_valid = verify_tribute_signature(headers, body)
    assert is_valid is True

    settings.webhook_secret = original_secret


def test_verify_tribute_signature_invalid():
    """Test signature verification with invalid signature."""
    original_secret = settings.webhook_secret
    settings.webhook_secret = "test_secret"

    body = b'{"test": "data"}'
    headers = {"X-Tribute-Signature": "invalid_signature"}

    is_valid = verify_tribute_signature(headers, body)
    assert is_valid is False

    settings.webhook_secret = original_secret


@pytest.mark.asyncio
async def test_apply_webhook_event_idempotency(test_db):
    """Test webhook idempotency (duplicate processing)."""
    payload = {
        "event_name": "payment.succeeded",
        "telegram_user_id": 123456789,
        "amount": 999,
        "currency": "USD",
    }
    raw_body = b'{"event_name": "payment.succeeded"}'
    headers = {"X-Tribute-Signature": "test_sig"}

    # Mock signature verification
    with patch("vechnost_bot.payments.services.verify_tribute_signature", return_value=True):
        # First call - should process
        result1 = await apply_webhook_event(payload, headers, raw_body)
        assert result1["status"] == "success"

        # Second call with same body - should be idempotent
        result2 = await apply_webhook_event(payload, headers, raw_body)
        assert result2["status"] == "success"
        assert "idempotent" in result2["message"].lower()


@pytest.mark.asyncio
async def test_apply_webhook_event_invalid_signature(test_db):
    """Test webhook with invalid signature."""
    payload = {
        "event_name": "payment.succeeded",
        "telegram_user_id": 123456789,
        "amount": 999,
        "currency": "USD",
    }
    raw_body = b'{"event_name": "payment.succeeded"}'
    headers = {"X-Tribute-Signature": "invalid_sig"}

    # Mock signature verification to fail
    with patch("vechnost_bot.payments.services.verify_tribute_signature", return_value=False):
        result = await apply_webhook_event(payload, headers, raw_body)
        assert result["status"] == "error"
        assert result["code"] == 401


@pytest.mark.asyncio
async def test_apply_webhook_event_subscription(test_db):
    """Test processing subscription webhook event."""
    payload = {
        "event_name": "subscription.renewed",
        "telegram_user_id": 123456789,
        "subscription_id": 1001,
        "amount": 999,
        "currency": "USD",
        "period": "month",
        "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat(),
    }
    raw_body = b'{"event_name": "subscription.renewed"}'
    headers = {"X-Tribute-Signature": "test_sig"}

    # Mock signature verification
    with patch("vechnost_bot.payments.services.verify_tribute_signature", return_value=True):
        result = await apply_webhook_event(payload, headers, raw_body)
        assert result["status"] == "success"

        # Verify subscription was created
        async with get_db() as session:
            user = await UserRepository.get_by_telegram_id(session, 123456789)
            assert user is not None

            subscriptions = await SubscriptionRepository.get_active_subscriptions_for_user(
                session, user.id
            )
            assert len(subscriptions) > 0

