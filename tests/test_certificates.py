"""Tests for certificate functionality."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vechnost_bot.payments.models import Certificate, User
from vechnost_bot.payments.repositories import CertificateRepository
from vechnost_bot.payments.services import activate_certificate, user_has_access


class TestCertificateModel:
    """Test Certificate model."""

    def test_certificate_creation(self):
        """Test certificate is created with correct defaults."""
        # Note: is_used gets its default from database (server_default='0')
        # When creating in-memory without DB, need to set explicitly
        cert = Certificate(code="VECH-TEST-1234", is_used=False)

        assert cert.code == "VECH-TEST-1234"
        assert cert.is_used is False  # Not used by default
        assert cert.used_by_telegram_user_id is None
        assert cert.used_at is None

    def test_is_valid_property_unused(self):
        """Test is_valid returns True for unused certificate."""
        cert = Certificate(code="VECH-TEST-1234", is_used=False)
        assert cert.is_valid is True

    def test_is_valid_property_used(self):
        """Test is_valid returns False for used certificate."""
        cert = Certificate(code="VECH-TEST-1234", is_used=True)
        assert cert.is_valid is False

    def test_certificate_repr(self):
        """Test certificate string representation."""
        cert = Certificate(id=1, code="VECH-TEST-1234", is_used=False)
        assert "VECH-TEST-1234" in repr(cert)
        assert "available" in repr(cert)

        cert_used = Certificate(id=1, code="VECH-TEST-1234", is_used=True)
        assert "used" in repr(cert_used)


@pytest.mark.asyncio
class TestCertificateActivation:
    """Test certificate activation logic."""

    async def test_activate_certificate_success(self):
        """Test successful certificate activation."""
        # Mock database session and repositories
        with patch('vechnost_bot.payments.services.get_db') as mock_get_db, \
             patch('vechnost_bot.payments.services.CertificateRepository') as mock_cert_repo, \
             patch('vechnost_bot.payments.services.UserRepository') as mock_user_repo:

            # Setup mocks
            mock_session = AsyncMock()
            mock_get_db.return_value.__aenter__.return_value = mock_session

            # Mock certificate
            mock_cert = MagicMock(spec=Certificate)
            mock_cert.id = 1
            mock_cert.code = "VECH-TEST-1234"
            mock_cert.is_used = False
            mock_cert.used_by_telegram_user_id = None
            mock_cert.used_at = None
            mock_cert_repo.get_by_code = AsyncMock(return_value=mock_cert)

            # Mock user
            mock_user = MagicMock(spec=User)
            mock_user.id = 1
            mock_user.telegram_user_id = 123456789
            mock_user_repo.create_or_update = AsyncMock(return_value=mock_user)

            # The claim is the one conditional UPDATE that decides who gets it
            mock_cert_repo.claim = AsyncMock(return_value=mock_cert)

            # Execute
            result = await activate_certificate(
                code="VECH-TEST-1234",
                telegram_user_id=123456789,
                username="testuser",
                first_name="Test",
                last_name="User"
            )

            # Verify
            assert result["status"] == "success"
            assert result["certificate_id"] == 1
            mock_user_repo.create_or_update.assert_called_once()
            mock_cert_repo.claim.assert_called_once_with(
                mock_session, "VECH-TEST-1234", 123456789
            )
            mock_session.commit.assert_called_once()

    async def test_a_claim_lost_to_a_simultaneous_redemption_is_a_409(self):
        """Both callers passed the `is_used` check; the UPDATE seated one."""
        with patch('vechnost_bot.payments.services.get_db') as mock_get_db, \
             patch('vechnost_bot.payments.services.CertificateRepository') as mock_cert_repo, \
             patch('vechnost_bot.payments.services.UserRepository') as mock_user_repo:

            mock_session = AsyncMock()
            mock_get_db.return_value.__aenter__.return_value = mock_session
            mock_cert = MagicMock(spec=Certificate)
            mock_cert.id = 1
            mock_cert.is_used = False
            mock_cert_repo.get_by_code = AsyncMock(return_value=mock_cert)
            mock_cert_repo.claim = AsyncMock(return_value=None)
            mock_user_repo.create_or_update = AsyncMock()

            result = await activate_certificate(code="VECH-TEST-1234", telegram_user_id=2)

            assert result["status"] == "error"
            assert result["code"] == 409
            mock_session.commit.assert_not_called()

    async def test_activate_certificate_not_found(self):
        """Test activation with non-existent certificate (404)."""
        with patch('vechnost_bot.payments.services.get_db') as mock_get_db, \
             patch('vechnost_bot.payments.services.CertificateRepository') as mock_cert_repo:

            mock_session = AsyncMock()
            mock_get_db.return_value.__aenter__.return_value = mock_session
            mock_cert_repo.get_by_code = AsyncMock(return_value=None)

            result = await activate_certificate(
                code="NONEXISTENT",
                telegram_user_id=123456789
            )

            assert result["status"] == "error"
            assert result["code"] == 404
            assert "not found" in result["message"].lower()

    async def test_activate_certificate_already_used(self):
        """Test activation of already used certificate (409) - one-time use enforcement."""
        with patch('vechnost_bot.payments.services.get_db') as mock_get_db, \
             patch('vechnost_bot.payments.services.CertificateRepository') as mock_cert_repo:

            mock_session = AsyncMock()
            mock_get_db.return_value.__aenter__.return_value = mock_session

            # Mock already used certificate
            mock_cert = MagicMock(spec=Certificate)
            mock_cert.code = "VECH-TEST-1234"
            mock_cert.is_used = True  # Already used!
            mock_cert.used_by_telegram_user_id = 987654321  # Used by another user
            mock_cert.used_at = datetime.utcnow()
            mock_cert_repo.get_by_code = AsyncMock(return_value=mock_cert)

            result = await activate_certificate(
                code="VECH-TEST-1234",
                telegram_user_id=123456789  # Different user trying to use
            )

            assert result["status"] == "error"
            assert result["code"] == 409
            assert "already used" in result["message"].lower()

    async def test_activate_certificate_different_user_cannot_reuse(self):
        """Test that different user cannot reuse certificate (requirement #3)."""
        with patch('vechnost_bot.payments.services.get_db') as mock_get_db, \
             patch('vechnost_bot.payments.services.CertificateRepository') as mock_cert_repo:

            mock_session = AsyncMock()
            mock_get_db.return_value.__aenter__.return_value = mock_session

            # Certificate already used by user 111
            mock_cert = MagicMock(spec=Certificate)
            mock_cert.is_used = True
            mock_cert.used_by_telegram_user_id = 111
            mock_cert_repo.get_by_code = AsyncMock(return_value=mock_cert)

            # User 222 tries to activate
            result = await activate_certificate(
                code="VECH-TEST-1234",
                telegram_user_id=222
            )

            assert result["status"] == "error"
            assert result["code"] == 409

    async def test_activate_certificate_creates_user(self):
        """Test that certificate activation creates user in database (requirement #1)."""
        with patch('vechnost_bot.payments.services.get_db') as mock_get_db, \
             patch('vechnost_bot.payments.services.CertificateRepository') as mock_cert_repo, \
             patch('vechnost_bot.payments.services.UserRepository') as mock_user_repo:

            mock_session = AsyncMock()
            mock_get_db.return_value.__aenter__.return_value = mock_session

            mock_cert = MagicMock(spec=Certificate)
            mock_cert.id = 1
            mock_cert.is_used = False
            mock_cert_repo.get_by_code = AsyncMock(return_value=mock_cert)
            mock_cert_repo.claim = AsyncMock(return_value=mock_cert)

            mock_user = MagicMock(spec=User)
            mock_user.id = 1
            mock_user.telegram_user_id = 123456789
            mock_user_repo.create_or_update = AsyncMock(return_value=mock_user)

            await activate_certificate(
                code="VECH-TEST-1234",
                telegram_user_id=123456789,
                username="testuser",
                first_name="Test",
                last_name="User"
            )

            # Verify user was created with full info
            mock_user_repo.create_or_update.assert_called_once_with(
                mock_session,
                telegram_user_id=123456789,
                username="testuser",
                first_name="Test",
                last_name="User"
            )


@pytest.mark.asyncio
class TestUserAccess:
    """Test user access logic with certificates."""

    async def test_user_has_access_with_activated_certificate(self):
        """Test that user has access after activating certificate (requirement #4)."""
        with patch('vechnost_bot.payments.services.get_db') as mock_get_db, \
             patch('vechnost_bot.payments.services.UserRepository') as mock_user_repo, \
             patch('vechnost_bot.payments.services.CertificateRepository') as mock_cert_repo, \
             patch('vechnost_bot.payments.services.SubscriptionRepository') as mock_sub_repo, \
             patch('vechnost_bot.payments.services.PaymentRepository') as mock_pay_repo, \
             patch('vechnost_bot.payments.services.settings') as mock_settings:

            mock_settings.enable_payment = True
            mock_session = AsyncMock()
            mock_get_db.return_value.__aenter__.return_value = mock_session

            # Mock user exists
            mock_user = MagicMock(spec=User)
            mock_user.id = 1
            mock_user_repo.get_by_telegram_id = AsyncMock(return_value=mock_user)

            # Mock no subscriptions or payments
            mock_sub_repo.get_active_subscriptions_for_user = AsyncMock(return_value=[])
            mock_pay_repo.get_active_payments_for_user = AsyncMock(return_value=[])

            # Mock activated certificate
            mock_cert = MagicMock(spec=Certificate)
            mock_cert.code = "VECH-TEST-1234"
            mock_cert.is_used = True
            mock_cert.used_by_telegram_user_id = 123456789
            mock_cert_repo.get_by_user = AsyncMock(return_value=[mock_cert])

            has_access = await user_has_access(123456789)

            assert has_access is True
            mock_cert_repo.get_by_user.assert_called_once_with(mock_session, 123456789)

    async def test_user_no_access_without_certificate(self):
        """Test that user has no access without certificate."""
        with patch('vechnost_bot.payments.services.get_db') as mock_get_db, \
             patch('vechnost_bot.payments.services.UserRepository') as mock_user_repo, \
             patch('vechnost_bot.payments.services.CertificateRepository') as mock_cert_repo, \
             patch('vechnost_bot.payments.services.SubscriptionRepository') as mock_sub_repo, \
             patch('vechnost_bot.payments.services.PaymentRepository') as mock_pay_repo, \
             patch('vechnost_bot.payments.services.settings') as mock_settings:

            mock_settings.enable_payment = True
            mock_session = AsyncMock()
            mock_get_db.return_value.__aenter__.return_value = mock_session

            mock_user = MagicMock(spec=User)
            mock_user.id = 1
            mock_user_repo.get_by_telegram_id = AsyncMock(return_value=mock_user)

            # No subscriptions, payments, or certificates
            mock_sub_repo.get_active_subscriptions_for_user = AsyncMock(return_value=[])
            mock_pay_repo.get_active_payments_for_user = AsyncMock(return_value=[])
            mock_cert_repo.get_by_user = AsyncMock(return_value=[])

            has_access = await user_has_access(123456789)

            assert has_access is False


@pytest.mark.asyncio
class TestCertificateRepository:
    """Test CertificateRepository methods."""

    async def test_mark_as_used_sets_all_fields(self):
        """Test that mark_as_used sets is_used, user_id, and timestamp (requirement #2)."""
        mock_session = AsyncMock()

        cert = Certificate(code="VECH-TEST-1234", is_used=False)
        user_id = 123456789

        result = await CertificateRepository.mark_as_used(mock_session, cert, user_id)

        assert result.is_used is True
        assert result.used_by_telegram_user_id == user_id
        assert result.used_at is not None
        assert isinstance(result.used_at, datetime)
        mock_session.flush.assert_called_once()

    async def test_get_by_user_returns_user_certificates(self):
        """Test getting certificates by user."""
        mock_session = AsyncMock()

        # Mock query result
        mock_result = MagicMock()
        mock_cert1 = MagicMock(spec=Certificate)
        mock_cert2 = MagicMock(spec=Certificate)
        mock_result.scalars.return_value.all.return_value = [mock_cert1, mock_cert2]
        mock_session.execute = AsyncMock(return_value=mock_result)

        certs = await CertificateRepository.get_by_user(mock_session, 123456789)

        assert len(certs) == 2
        mock_session.execute.assert_called_once()


@pytest.fixture
def memory_db():
    """A fresh in-memory database with payments switched on."""
    from unittest.mock import patch as _patch

    import vechnost_bot.payments.database as database
    from vechnost_bot.config import settings

    with (
        _patch.object(settings, "database_url", "sqlite+aiosqlite:///:memory:"),
        _patch.object(database, "engine", None),
        _patch.object(database, "async_session_maker", None),
        _patch.object(database, "_tables_created", False),
        _patch.object(settings, "enable_payment", True),
    ):
        yield


@pytest.mark.integration
class TestCertificateIntegration:
    """The whole flow against a real (in-memory) database.

    These two were `pass` stubs for months, counting as green while the
    activation path did a read-then-write that two simultaneous
    redemptions could both pass.
    """

    async def test_complete_certificate_flow(self, memory_db):
        """generate -> activate -> access -> a second redemption is refused."""
        from vechnost_bot.payments.database import get_db
        from vechnost_bot.payments.gifts import create_gift_certificate

        async with get_db() as session:
            code = await create_gift_certificate(session)

        assert await user_has_access(111) is False
        first = await activate_certificate(code=code, telegram_user_id=111)
        assert first["status"] == "success"
        assert await user_has_access(111) is True

        second = await activate_certificate(code=code, telegram_user_id=222)
        assert second["status"] == "error" and second["code"] == 409
        assert await user_has_access(222) is False

        async with get_db() as session:
            certificate = await CertificateRepository.get_by_code(session, code)
        assert certificate.is_used is True
        assert certificate.used_by_telegram_user_id == 111

    async def test_concurrent_activation_race_condition(self, memory_db):
        """Two redemptions of one code: the UPDATE's WHERE clause seats one.

        SQLite has no concurrent writers, so this exercises the mechanism
        rather than the interleaving: the second `claim` finds no row with
        `is_used = false` to change and comes back empty, which is exactly
        what the loser of a real race on Postgres sees.
        """
        from vechnost_bot.payments.database import get_db
        from vechnost_bot.payments.gifts import create_gift_certificate

        async with get_db() as session:
            code = await create_gift_certificate(session)

        async with get_db() as session:
            winner = await CertificateRepository.claim(session, code, 111)
            loser = await CertificateRepository.claim(session, code, 222)

        assert winner is not None and winner.used_by_telegram_user_id == 111
        assert loser is None

