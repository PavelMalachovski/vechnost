"""Tests for certificate functionality."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from vechnost_bot.payments.models import Certificate, User
from vechnost_bot.payments.repositories import CertificateRepository, UserRepository
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

            # Mock mark as used
            mock_cert_repo.mark_as_used = AsyncMock(return_value=mock_cert)

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
            mock_cert_repo.mark_as_used.assert_called_once()
            mock_session.commit.assert_called_once()

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
            mock_cert_repo.mark_as_used = AsyncMock(return_value=mock_cert)

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


@pytest.mark.integration
@pytest.mark.asyncio
class TestCertificateIntegration:
    """Integration tests for certificate flow."""

    async def test_complete_certificate_flow(self):
        """Test complete flow: generate -> activate -> verify access -> reject reuse."""
        # This would require actual database connection
        # Placeholder for integration test
        pass

    async def test_concurrent_activation_race_condition(self):
        """Test that concurrent activations don't create race conditions."""
        # This would test the critical race condition scenario
        # where two users try to activate the same certificate simultaneously
        pass

