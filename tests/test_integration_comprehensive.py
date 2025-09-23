"""Comprehensive integration tests for complete user flows."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from vechnost_bot.models import SessionState, Language, Theme, ContentType
from vechnost_bot.exceptions import VechnostBotError, ErrorCodes
from vechnost_bot.handlers import start_command, handle_callback_query
from vechnost_bot.callback_handlers import CallbackHandlerRegistry
from vechnost_bot.storage import get_session, reset_session


class TestCompleteUserFlows:
    """Test complete user journeys through the bot."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_complete_acquaintance_flow(
        self,
        mock_update,
        mock_context,
        hybrid_storage_with_memory,
        mock_translations
    ):
        """Test complete Acquaintance theme flow."""
        # Mock the storage
        with patch('vechnost_bot.storage.get_hybrid_storage', return_value=hybrid_storage_with_memory):
            # Step 1: Start command
            with patch('vechnost_bot.handlers.get_language_selection_keyboard') as mock_keyboard, \
                 patch('vechnost_bot.handlers.detect_language_from_text') as mock_detect, \
                 patch('vechnost_bot.handlers.open') as mock_open, \
                 patch('vechnost_bot.handlers.set_user_context') as mock_set_context:

                mock_detect.return_value = Language.ENGLISH
                mock_keyboard.return_value = MagicMock()
                mock_open.return_value.__enter__.return_value = MagicMock()
                mock_update.message.reply_photo = AsyncMock()

                await start_command(mock_update, mock_context)

                # Verify language selection was sent
                mock_update.message.reply_photo.assert_called_once()
                mock_set_context.assert_called_once()

            # Step 2: Language selection
            mock_update.callback_query.data = "lang_en"
            mock_update.callback_query.edit_message_text = AsyncMock()
            mock_update.callback_query.delete_message = AsyncMock()
            mock_update.message.reply_text = AsyncMock()

            await handle_callback_query(mock_update, mock_context)

            # Verify session was created with English language
            session = await get_session(12345)
            assert session.language == Language.ENGLISH

            # Step 3: Theme selection
            mock_update.callback_query.data = "theme_Acquaintance"
            mock_update.callback_query.edit_message_text = AsyncMock()

            await handle_callback_query(mock_update, mock_context)

            # Verify theme was set
            session = await get_session(12345)
            assert session.theme == Theme.ACQUAINTANCE

            # Step 4: Level selection
            mock_update.callback_query.data = "level_1"
            mock_update.callback_query.edit_message_text = AsyncMock()

            await handle_callback_query(mock_update, mock_context)

            # Verify level was set
            session = await get_session(12345)
            assert session.level == 1
            assert session.content_type == ContentType.QUESTIONS

            # Step 5: Question selection
            mock_update.callback_query.data = "q:acq:1:0"
            mock_update.callback_query.edit_message_text = AsyncMock()

            await handle_callback_query(mock_update, mock_context)

            # Verify question was displayed
            mock_update.callback_query.edit_message_text.assert_called()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_complete_sex_theme_flow(
        self,
        mock_update,
        mock_context,
        hybrid_storage_with_memory
    ):
        """Test complete Sex theme flow with NSFW confirmation."""
        with patch('vechnost_bot.storage.get_hybrid_storage', return_value=hybrid_storage_with_memory):
            # Step 1: Language selection
            mock_update.callback_query.data = "lang_en"
            await handle_callback_query(mock_update, mock_context)

            # Step 2: Sex theme selection
            mock_update.callback_query.data = "theme_Sex"
            mock_update.callback_query.edit_message_text = AsyncMock()

            await handle_callback_query(mock_update, mock_context)

            # Verify NSFW warning was shown
            session = await get_session(12345)
            assert session.theme == Theme.SEX
            assert not session.is_nsfw_confirmed

            # Step 3: NSFW confirmation
            mock_update.callback_query.data = "nsfw_confirm"
            mock_update.callback_query.edit_message_text = AsyncMock()

            await handle_callback_query(mock_update, mock_context)

            # Verify NSFW was confirmed and calendar shown
            session = await get_session(12345)
            assert session.is_nsfw_confirmed
            assert session.content_type == ContentType.QUESTIONS

            # Step 4: Toggle to tasks
            mock_update.callback_query.data = "toggle:tasks"
            mock_update.callback_query.edit_message_text = AsyncMock()

            await handle_callback_query(mock_update, mock_context)

            # Verify content type changed to tasks
            session = await get_session(12345)
            assert session.content_type == ContentType.TASKS

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_complete_reset_flow(
        self,
        mock_update,
        mock_context,
        hybrid_storage_with_memory
    ):
        """Test complete reset flow."""
        with patch('vechnost_bot.storage.get_hybrid_storage', return_value=hybrid_storage_with_memory):
            # Step 1: Create a session with data
            mock_update.callback_query.data = "lang_en"
            await handle_callback_query(mock_update, mock_context)

            mock_update.callback_query.data = "theme_Acquaintance"
            await handle_callback_query(mock_update, mock_context)

            mock_update.callback_query.data = "level_1"
            await handle_callback_query(mock_update, mock_context)

            # Verify session has data
            session = await get_session(12345)
            assert session.theme == Theme.ACQUAINTANCE
            assert session.level == 1

            # Step 2: Reset command
            mock_update.callback_query.data = "reset_game"
            mock_update.callback_query.edit_message_text = AsyncMock()

            await handle_callback_query(mock_update, mock_context)

            # Step 3: Confirm reset
            mock_update.callback_query.data = "reset_confirm"
            mock_update.callback_query.edit_message_text = AsyncMock()

            await handle_callback_query(mock_update, mock_context)

            # Verify session was reset
            session = await get_session(12345)
            assert session.theme is None
            assert session.level is None
            assert session.language == Language.ENGLISH  # Language should be preserved

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_complete_navigation_flow(
        self,
        mock_update,
        mock_context,
        hybrid_storage_with_memory
    ):
        """Test complete navigation flow."""
        with patch('vechnost_bot.storage.get_hybrid_storage', return_value=hybrid_storage_with_memory):
            # Step 1: Navigate to question
            mock_update.callback_query.data = "lang_en"
            await handle_callback_query(mock_update, mock_context)

            mock_update.callback_query.data = "theme_Acquaintance"
            await handle_callback_query(mock_update, mock_context)

            mock_update.callback_query.data = "level_1"
            await handle_callback_query(mock_update, mock_context)

            mock_update.callback_query.data = "q:acq:1:0"
            await handle_callback_query(mock_update, mock_context)

            # Step 2: Navigate to next question
            mock_update.callback_query.data = "nav:next"
            mock_update.callback_query.edit_message_text = AsyncMock()

            await handle_callback_query(mock_update, mock_context)

            # Step 3: Navigate to previous question
            mock_update.callback_query.data = "nav:prev"
            mock_update.callback_query.edit_message_text = AsyncMock()

            await handle_callback_query(mock_update, mock_context)

            # Step 4: Navigate back to calendar
            mock_update.callback_query.data = "back:calendar"
            mock_update.callback_query.edit_message_text = AsyncMock()

            await handle_callback_query(mock_update, mock_context)

            # Step 5: Navigate back to levels
            mock_update.callback_query.data = "back:levels"
            mock_update.callback_query.edit_message_text = AsyncMock()

            await handle_callback_query(mock_update, mock_context)

            # Step 6: Navigate back to themes
            mock_update.callback_query.data = "back:themes"
            mock_update.callback_query.edit_message_text = AsyncMock()

            await handle_callback_query(mock_update, mock_context)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_multilingual_flow(
        self,
        mock_update,
        mock_context,
        hybrid_storage_with_memory
    ):
        """Test multilingual flow switching between languages."""
        with patch('vechnost_bot.storage.get_hybrid_storage', return_value=hybrid_storage_with_memory):
            # Step 1: Start with English
            mock_update.callback_query.data = "lang_en"
            await handle_callback_query(mock_update, mock_context)

            session = await get_session(12345)
            assert session.language == Language.ENGLISH

            # Step 2: Switch to Russian
            mock_update.callback_query.data = "lang_ru"
            await handle_callback_query(mock_update, mock_context)

            session = await get_session(12345)
            assert session.language == Language.RUSSIAN

            # Step 3: Switch to Czech
            mock_update.callback_query.data = "lang_cs"
            await handle_callback_query(mock_update, mock_context)

            session = await get_session(12345)
            assert session.language == Language.CZECH

            # Step 4: Navigate through theme in Czech
            mock_update.callback_query.data = "theme_Acquaintance"
            await handle_callback_query(mock_update, mock_context)

            mock_update.callback_query.data = "level_1"
            await handle_callback_query(mock_update, mock_context)

            # Verify session maintains Czech language
            session = await get_session(12345)
            assert session.language == Language.CZECH
            assert session.theme == Theme.ACQUAINTANCE


class TestErrorRecoveryScenarios:
    """Test error recovery mechanisms."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_invalid_callback_data_recovery(
        self,
        mock_update,
        mock_context,
        hybrid_storage_with_memory
    ):
        """Test recovery from invalid callback data."""
        with patch('vechnost_bot.storage.get_hybrid_storage', return_value=hybrid_storage_with_memory):
            # Step 1: Valid callback
            mock_update.callback_query.data = "lang_en"
            await handle_callback_query(mock_update, mock_context)

            # Step 2: Invalid callback
            mock_update.callback_query.data = "invalid_callback_data"
            mock_update.callback_query.edit_message_text = AsyncMock()

            await handle_callback_query(mock_update, mock_context)

            # Verify error message was sent
            mock_update.callback_query.edit_message_text.assert_called()

            # Verify session is still intact
            session = await get_session(12345)
            assert session.language == Language.ENGLISH

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_storage_failure_recovery(
        self,
        mock_update,
        mock_context,
        mock_redis_error
    ):
        """Test recovery from storage failures."""
        with patch('vechnost_bot.storage.get_hybrid_storage') as mock_get_storage:
            # Mock storage that fails
            mock_storage = AsyncMock()
            mock_storage.get_session.side_effect = mock_redis_error
            mock_storage.save_session.side_effect = mock_redis_error
            mock_get_storage.return_value = mock_storage

            # Step 1: Try to handle callback with failing storage
            mock_update.callback_query.data = "lang_en"
            mock_update.callback_query.edit_message_text = AsyncMock()

            # Should not raise exception, should handle gracefully
            await handle_callback_query(mock_update, mock_context)

            # Verify error message was sent
            mock_update.callback_query.edit_message_text.assert_called()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_telegram_api_failure_recovery(
        self,
        mock_update,
        mock_context,
        hybrid_storage_with_memory,
        mock_telegram_error
    ):
        """Test recovery from Telegram API failures."""
        with patch('vechnost_bot.storage.get_hybrid_storage', return_value=hybrid_storage_with_memory):
            # Mock Telegram API failure
            mock_update.callback_query.edit_message_text.side_effect = mock_telegram_error
            mock_update.message.reply_text = AsyncMock()

            # Step 1: Handle callback with failing Telegram API
            mock_update.callback_query.data = "lang_en"

            # Should not raise exception, should handle gracefully
            await handle_callback_query(mock_update, mock_context)

            # Verify fallback message was sent
            mock_update.message.reply_text.assert_called()


class TestPerformanceScenarios:
    """Test performance scenarios."""

    @pytest.mark.integration
    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_concurrent_user_sessions(
        self,
        hybrid_storage_with_memory,
        performance_timer
    ):
        """Test concurrent user sessions."""
        async def create_user_session(user_id: int):
            """Create a session for a user."""
            session = SessionState(
                language=Language.ENGLISH,
                theme=Theme.ACQUAINTANCE,
                level=1
            )
            await hybrid_storage_with_memory.save_session(user_id, session)
            return await hybrid_storage_with_memory.get_session(user_id)

        # Create multiple concurrent sessions
        user_ids = list(range(100))
        sessions = await asyncio.gather(*[
            create_user_session(user_id) for user_id in user_ids
        ])

        # Verify all sessions were created
        assert len(sessions) == 100
        for session in sessions:
            assert session is not None
            assert session.language == Language.ENGLISH
            assert session.theme == Theme.ACQUAINTANCE

        # Check performance
        elapsed_time = performance_timer()
        assert elapsed_time < 5.0  # Should complete within 5 seconds

    @pytest.mark.integration
    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_rapid_callback_handling(
        self,
        mock_update,
        mock_context,
        hybrid_storage_with_memory,
        performance_timer
    ):
        """Test rapid callback handling."""
        with patch('vechnost_bot.storage.get_hybrid_storage', return_value=hybrid_storage_with_memory):
            callbacks = [
                "lang_en",
                "theme_Acquaintance",
                "level_1",
                "q:acq:1:0",
                "nav:next",
                "nav:next",
                "nav:prev",
                "back:calendar",
                "back:levels",
                "back:themes"
            ]

            # Handle all callbacks rapidly
            for callback_data in callbacks:
                mock_update.callback_query.data = callback_data
                await handle_callback_query(mock_update, mock_context)

            # Check performance
            elapsed_time = performance_timer()
            assert elapsed_time < 2.0  # Should complete within 2 seconds

            # Verify final session state
            session = await get_session(12345)
            assert session.language == Language.ENGLISH


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_empty_session_handling(
        self,
        mock_update,
        mock_context,
        hybrid_storage_with_memory
    ):
        """Test handling of empty sessions."""
        with patch('vechnost_bot.storage.get_hybrid_storage', return_value=hybrid_storage_with_memory):
            # Try to navigate without setting up session
            mock_update.callback_query.data = "theme_Acquaintance"
            mock_update.callback_query.edit_message_text = AsyncMock()

            await handle_callback_query(mock_update, mock_context)

            # Should handle gracefully and create session
            session = await get_session(12345)
            assert session is not None
            assert session.theme == Theme.ACQUAINTANCE

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_session_state_corruption_recovery(
        self,
        mock_update,
        mock_context,
        hybrid_storage_with_memory
    ):
        """Test recovery from corrupted session state."""
        with patch('vechnost_bot.storage.get_hybrid_storage', return_value=hybrid_storage_with_memory):
            # Create a corrupted session
            corrupted_session = SessionState(
                language=Language.ENGLISH,
                theme=Theme.ACQUAINTANCE,
                level=999  # Invalid level
            )
            await hybrid_storage_with_memory.save_session(12345, corrupted_session)

            # Try to navigate with corrupted session
            mock_update.callback_query.data = "q:acq:999:0"
            mock_update.callback_query.edit_message_text = AsyncMock()

            await handle_callback_query(mock_update, mock_context)

            # Should handle gracefully
            mock_update.callback_query.edit_message_text.assert_called()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_memory_limit_handling(
        self,
        hybrid_storage_with_memory,
        performance_timer
    ):
        """Test handling of memory limits."""
        # Create many sessions to test memory handling
        sessions = []
        for i in range(1000):
            session = SessionState(
                language=Language.ENGLISH,
                theme=Theme.ACQUAINTANCE,
                level=1
            )
            await hybrid_storage_with_memory.save_session(i, session)
            sessions.append(await hybrid_storage_with_memory.get_session(i))

        # Verify all sessions are accessible
        assert len(sessions) == 1000
        for session in sessions:
            assert session is not None

        # Check performance
        elapsed_time = performance_timer()
        assert elapsed_time < 10.0  # Should complete within 10 seconds


class TestDataIntegrity:
    """Test data integrity and consistency."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_session_persistence_across_operations(
        self,
        mock_update,
        mock_context,
        hybrid_storage_with_memory
    ):
        """Test session persistence across multiple operations."""
        with patch('vechnost_bot.storage.get_hybrid_storage', return_value=hybrid_storage_with_memory):
            # Step 1: Set up session
            mock_update.callback_query.data = "lang_en"
            await handle_callback_query(mock_update, mock_context)

            mock_update.callback_query.data = "theme_Acquaintance"
            await handle_callback_query(mock_update, mock_context)

            # Step 2: Verify session state
            session1 = await get_session(12345)
            assert session1.language == Language.ENGLISH
            assert session1.theme == Theme.ACQUAINTANCE

            # Step 3: Perform more operations
            mock_update.callback_query.data = "level_1"
            await handle_callback_query(mock_update, mock_context)

            mock_update.callback_query.data = "q:acq:1:0"
            await handle_callback_query(mock_update, mock_context)

            # Step 4: Verify session state is still consistent
            session2 = await get_session(12345)
            assert session2.language == Language.ENGLISH
            assert session2.theme == Theme.ACQUAINTANCE
            assert session2.level == 1
            assert session2.content_type == ContentType.QUESTIONS

            # Step 5: Verify session objects are the same instance
            assert session1.language == session2.language
            assert session1.theme == session2.theme

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_concurrent_session_modifications(
        self,
        hybrid_storage_with_memory
    ):
        """Test concurrent modifications to the same session."""
        async def modify_session(operation: str):
            """Modify session with given operation."""
            session = await hybrid_storage_with_memory.get_session(12345)
            if session is None:
                session = SessionState()

            if operation == "set_language":
                session.language = Language.ENGLISH
            elif operation == "set_theme":
                session.theme = Theme.ACQUAINTANCE
            elif operation == "set_level":
                session.level = 1

            await hybrid_storage_with_memory.save_session(12345, session)
            return session

        # Perform concurrent modifications
        operations = ["set_language", "set_theme", "set_level"]
        sessions = await asyncio.gather(*[
            modify_session(op) for op in operations
        ])

        # Verify final session state
        final_session = await hybrid_storage_with_memory.get_session(12345)
        assert final_session is not None
        assert final_session.language == Language.ENGLISH
        assert final_session.theme == Theme.ACQUAINTANCE
        assert final_session.level == 1
