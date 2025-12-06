# Vechnost Bot - Анализ кодовой базы и предложение новых функций

**Дата анализа:** 6 декабря 2025
**Версия проекта:** 1.0.0
**Проанализировано модулей:** 38 Python файлов + 33 документа

---

## 📊 Общая оценка проекта

### Сильные стороны ✅

1. **Архитектура:**
   - ✅ Чистая архитектура с правильным разделением на слои (представление, бизнес-логика, доступ к данным)
   - ✅ Repository Pattern для абстракции работы с БД
   - ✅ Service Layer Pattern для инкапсуляции бизнес-логики
   - ✅ Registry Pattern для маршрутизации callback-запросов
   - ✅ Singleton Pattern для глобальных менеджеров (i18n, settings)

2. **Качество кода:**
   - ✅ Строгая типизация с Mypy (Python 3.11+)
   - ✅ Современные аннотации типов (`list[str]` вместо `List[str]`)
   - ✅ Docstrings в Google-стиле для всех публичных функций
   - ✅ Ruff для линтинга (100 символов на строку)
   - ✅ Async/await везде где нужно

3. **Функциональность:**
   - ✅ Многоязычность (русский, английский, чешский) через Babel
   - ✅ Интеграция платежей через Tribute API
   - ✅ Система сертификатов для бесплатного доступа
   - ✅ Redis для управления сессиями с TTL
   - ✅ SQLAlchemy 2.0+ с миграциями Alembic
   - ✅ Рендеринг карточек с вопросами в PNG/JPEG
   - ✅ Структурированное логирование (structlog) и Sentry

4. **Тестирование:**
   - ✅ Pytest с async поддержкой
   - ✅ Покрытие тестами ~80%
   - ✅ Комплексные unit и integration тесты
   - ✅ Мокирование внешних зависимостей

5. **DevOps:**
   - ✅ Docker с multi-stage сборкой
   - ✅ Готовность к деплою на Render.com и Railway
   - ✅ Автоматические миграции БД
   - ✅ Health check endpoints
   - ✅ Environment variables validation через Pydantic

### Области для улучшения ⚠️

1. **Производительность:**
   - ⚠️ Отсутствие кеширования часто запрашиваемых данных (игровой контент)
   - ⚠️ Рендеринг изображений может быть медленным при высокой нагрузке
   - ⚠️ Нет rate limiting для обработки сообщений (только для webhook)
   - ⚠️ Connection pooling для Redis настроен (max_connections=20), но можно оптимизировать

2. **Функциональность:**
   - ⚠️ Отсутствие голосового ввода (voice messages)
   - ⚠️ Нет аналитики действий пользователей (какие темы/вопросы популярны)
   - ⚠️ Отсутствие персонализации (рекомендации на основе истории)
   - ⚠️ Нет групповых игр/сессий
   - ⚠️ Отсутствие напоминаний/уведомлений для регулярного использования
   - ⚠️ Нет системы достижений/геймификации

3. **Безопасность:**
   - ⚠️ CSRF protection реализован но не используется в handlers
   - ⚠️ Input sanitization есть, но не применяется везде
   - ⚠️ Отсутствие rate limiting на уровне пользователя для команд бота

4. **Мониторинг:**
   - ⚠️ Sentry настроен, но можно добавить больше метрик (Prometheus/Grafana)
   - ⚠️ Отсутствие алертов при критических ошибках
   - ⚠️ Нет dashboard для мониторинга здоровья системы

---

## 🚀 Предложения по новым функциям

### 1. 🎤 Интеграция OpenAI Whisper для голосового ввода (ПРИОРИТЕТ: ВЫСОКИЙ)

#### Описание
Добавить возможность пользователям отправлять голосовые сообщения вместо текстовых ответов на вопросы. Whisper API от OpenAI преобразует голос в текст на любом из поддерживаемых языков.

#### Преимущества
- 🗣️ **Естественность общения:** Пользователи могут отвечать голосом, что делает игру более интимной
- 🌍 **Многоязычность:** Whisper поддерживает 50+ языков, включая русский, английский и чешский
- ⚡ **Быстрота:** Транскрибация происходит за 2-3 секунды
- ♿ **Доступность:** Удобно для людей, которым сложно печатать
- 📊 **Аналитика:** Можно анализировать длину и эмоциональность ответов

#### Техническая реализация

```python
# vechnost_bot/voice_handler.py
"""Voice message handler using OpenAI Whisper API."""

import logging
from pathlib import Path
from typing import Optional
import aiofiles
from openai import AsyncOpenAI
from telegram import Update, Voice
from telegram.ext import ContextTypes

from .config import settings
from .i18n import Language, get_text
from .monitoring import track_performance, log_bot_event

logger = logging.getLogger(__name__)


class VoiceTranscriptionService:
    """Service for transcribing voice messages using OpenAI Whisper."""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.temp_dir = Path("temp/voice")
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    @track_performance("transcribe_voice")
    async def transcribe_voice_message(
        self,
        voice: Voice,
        language: Language,
        context: ContextTypes.DEFAULT_TYPE
    ) -> Optional[str]:
        """
        Transcribe a Telegram voice message to text.

        Args:
            voice: Telegram Voice object
            language: Target language for transcription
            context: Bot context for file download

        Returns:
            Transcribed text or None if error
        """
        temp_file = None
        try:
            # Download voice file
            voice_file = await context.bot.get_file(voice.file_id)
            temp_file = self.temp_dir / f"{voice.file_id}.ogg"

            await voice_file.download_to_drive(temp_file)

            logger.info(
                f"Voice file downloaded: {temp_file} "
                f"(duration: {voice.duration}s, size: {voice.file_size} bytes)"
            )

            # Transcribe using Whisper
            async with aiofiles.open(temp_file, "rb") as audio_file:
                audio_data = await audio_file.read()

                transcription = await self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=("audio.ogg", audio_data, "audio/ogg"),
                    response_format="verbose_json",
                    language=language.value,  # en, ru, cs
                    temperature=0.0,  # More deterministic
                )

            text = transcription.text
            detected_language = transcription.language
            duration = transcription.duration

            logger.info(
                f"Voice transcribed successfully: length={len(text)}, "
                f"detected_language={detected_language}, duration={duration}s"
            )

            log_bot_event(
                "voice_transcribed",
                text_length=len(text),
                voice_duration=voice.duration,
                detected_language=detected_language,
            )

            return text

        except Exception as e:
            logger.error(f"Error transcribing voice message: {e}", exc_info=True)
            log_bot_event("voice_transcription_error", error=str(e))
            return None

        finally:
            # Cleanup temp file
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {temp_file}: {e}")


# Global service instance
voice_service = VoiceTranscriptionService()


async def handle_voice_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle incoming voice messages.

    Args:
        update: Telegram update with voice message
        context: Bot context
    """
    if not update.message or not update.message.voice:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # Import here to avoid circular dependency
    from .storage import get_session

    # Get user session for language preference
    session = await get_session(chat_id)
    language = session.language

    # Show "typing..." indicator
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # Inform user about transcription
    processing_msg = await update.message.reply_text(
        get_text("voice.processing", language)
    )

    # Transcribe voice message
    transcribed_text = await voice_service.transcribe_voice_message(
        update.message.voice, language, context
    )

    # Delete processing message
    await processing_msg.delete()

    if transcribed_text:
        # Send transcribed text back to user
        response = get_text("voice.transcribed", language).format(
            text=transcribed_text
        )
        await update.message.reply_text(response)

        # Log the interaction
        log_bot_event(
            "voice_message_handled",
            user_id=user_id,
            text_length=len(transcribed_text),
        )
    else:
        # Error occurred
        error_msg = get_text("voice.error", language)
        await update.message.reply_text(error_msg)


# Add to bot.py:
# from .voice_handler import handle_voice_message
# application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
```

#### Изменения в конфигурации

```python
# vechnost_bot/config.py - добавить в Settings класс:

openai_api_key: Optional[str] = Field(
    default=None,
    validation_alias="OPENAI_API_KEY",
    description="OpenAI API key for Whisper transcription"
)

enable_voice_transcription: bool = Field(
    default=False,
    validation_alias="ENABLE_VOICE_TRANSCRIPTION",
    description="Enable voice message transcription"
)
```

#### Переводы для голосовых сообщений

```yaml
# data/translations_ru.yaml
voice:
  processing: "🎤 Распознаю голосовое сообщение..."
  transcribed: "📝 Вы сказали:\n\n{text}"
  error: "❌ Не удалось распознать голосовое сообщение. Попробуйте ещё раз."
  not_enabled: "🔇 Голосовые сообщения пока не поддерживаются."

# data/translations_en.yaml
voice:
  processing: "🎤 Transcribing voice message..."
  transcribed: "📝 You said:\n\n{text}"
  error: "❌ Failed to transcribe voice message. Please try again."
  not_enabled: "🔇 Voice messages are not supported yet."

# data/translations_cs.yaml
voice:
  processing: "🎤 Přepisuji hlasovou zprávu..."
  transcribed: "📝 Řekli jste:\n\n{text}"
  error: "❌ Nepodařilo se přepsat hlasovou zprávu. Zkuste to znovu."
  not_enabled: "🔇 Hlasové zprávy zatím nejsou podporovány."
```

#### Зависимости

```toml
# pyproject.toml - добавить в dependencies:
"openai>=1.68.0",  # For Whisper API
"aiofiles>=23.0.0",  # Already present
```

#### Тесты

```python
# tests/test_voice_handler.py
"""Tests for voice message handler."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from vechnost_bot.voice_handler import VoiceTranscriptionService, handle_voice_message
from vechnost_bot.i18n import Language


class TestVoiceTranscriptionService:
    """Test voice transcription service."""

    @pytest.mark.asyncio
    async def test_transcribe_voice_success(self):
        """Test successful voice transcription."""
        service = VoiceTranscriptionService()

        # Mock OpenAI client
        with patch.object(service, 'client') as mock_client:
            mock_response = MagicMock()
            mock_response.text = "Привет, как дела?"
            mock_response.language = "ru"
            mock_response.duration = 3.5

            mock_client.audio.transcriptions.create = AsyncMock(
                return_value=mock_response
            )

            # Mock Telegram objects
            voice = MagicMock()
            voice.file_id = "test_file_id"
            voice.duration = 3
            voice.file_size = 12345

            context = MagicMock()
            voice_file = MagicMock()
            voice_file.download_to_drive = AsyncMock()
            context.bot.get_file = AsyncMock(return_value=voice_file)

            # Transcribe
            result = await service.transcribe_voice_message(
                voice, Language.RUSSIAN, context
            )

            assert result == "Привет, как дела?"
            mock_client.audio.transcriptions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_transcribe_voice_error(self):
        """Test voice transcription error handling."""
        service = VoiceTranscriptionService()

        # Mock OpenAI client to raise exception
        with patch.object(service, 'client') as mock_client:
            mock_client.audio.transcriptions.create = AsyncMock(
                side_effect=Exception("API Error")
            )

            voice = MagicMock()
            voice.file_id = "test_file_id"
            context = MagicMock()
            context.bot.get_file = AsyncMock()

            result = await service.transcribe_voice_message(
                voice, Language.RUSSIAN, context
            )

            assert result is None


class TestVoiceMessageHandler:
    """Test voice message handler."""

    @pytest.mark.asyncio
    async def test_handle_voice_message(self):
        """Test handling of voice message."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.voice = MagicMock()
        update.effective_chat = MagicMock()
        update.effective_chat.id = 12345
        update.effective_user = MagicMock()
        update.effective_user.id = 67890

        context = MagicMock()
        context.bot.send_chat_action = AsyncMock()
        update.message.reply_text = AsyncMock()

        # Mock voice service
        with patch('vechnost_bot.voice_handler.voice_service') as mock_service:
            mock_service.transcribe_voice_message = AsyncMock(
                return_value="Test transcription"
            )

            await handle_voice_message(update, context)

            # Verify transcription was called
            mock_service.transcribe_voice_message.assert_called_once()

            # Verify response was sent
            update.message.reply_text.assert_called()
```

#### Стоимость и производительность

- **Стоимость:** $0.006 за минуту аудио (Whisper API)
- **Средняя длина голосового сообщения:** 10-30 секунд
- **Стоимость на сообщение:** ~$0.001-0.003
- **Время транскрибации:** 2-5 секунд
- **Rate limit:** 50 запросов в минуту (OpenAI default)

#### Дорожная карта реализации

1. **Фаза 1 (1-2 дня):**
   - Добавить OpenAI SDK в зависимости
   - Реализовать `VoiceTranscriptionService`
   - Добавить обработчик голосовых сообщений
   - Написать unit тесты

2. **Фаза 2 (1 день):**
   - Добавить переводы для всех языков
   - Интегрировать с существующими handlers
   - Добавить мониторинг и логирование

3. **Фаза 3 (1-2 дня):**
   - Тестирование на продакшене с малой группой
   - Оптимизация производительности
   - Документация для пользователей

---

### 2. 🎙️ Генерация голосовых вопросов через OpenAI TTS (ПРИОРИТЕТ: СРЕДНИЙ)

#### Описание
Помимо приема голоса от пользователя, можно озвучивать сами вопросы из карточек через OpenAI Text-to-Speech API. Это сделает игру еще более интерактивной.

#### Преимущества
- 🎭 **Атмосфера:** Голосовое озвучивание создает уникальную атмосферу
- 👂 **Удобство:** Можно слушать вопросы вместо чтения
- 🌐 **Многоязычность:** TTS поддерживает все языки бота
- ♿ **Доступность:** Помощь людям с ограничениями зрения

#### Техническая реализация

```python
# vechnost_bot/tts_service.py
"""Text-to-speech service using OpenAI TTS API."""

import logging
from pathlib import Path
from typing import Optional
import hashlib
from openai import AsyncOpenAI

from .config import settings
from .i18n import Language
from .monitoring import track_performance

logger = logging.getLogger(__name__)


class TTSService:
    """Service for converting text to speech."""

    # Voice mapping for different languages
    VOICE_MAP = {
        Language.RUSSIAN: "nova",  # Female voice, sounds good in Russian
        Language.ENGLISH: "alloy",  # Neutral voice
        Language.CZECH: "shimmer",  # Female voice
    }

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.cache_dir = Path("cache/tts")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(self, text: str, language: Language) -> str:
        """Generate cache key for TTS audio."""
        content = f"{text}:{language.value}".encode('utf-8')
        return hashlib.sha256(content).hexdigest()[:16]

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get cache file path."""
        return self.cache_dir / f"{cache_key}.mp3"

    @track_performance("generate_tts")
    async def text_to_speech(
        self,
        text: str,
        language: Language
    ) -> Optional[Path]:
        """
        Convert text to speech audio file.

        Args:
            text: Text to convert
            language: Language for speech synthesis

        Returns:
            Path to audio file or None if error
        """
        try:
            # Check cache first
            cache_key = self._get_cache_key(text, language)
            cache_path = self._get_cache_path(cache_key)

            if cache_path.exists():
                logger.debug(f"TTS cache hit: {cache_key}")
                return cache_path

            # Generate speech
            voice = self.VOICE_MAP.get(language, "alloy")

            response = await self.client.audio.speech.create(
                model="tts-1",  # or "tts-1-hd" for higher quality
                voice=voice,
                input=text[:4096],  # TTS API limit
                response_format="mp3",
            )

            # Save to cache
            await response.awrite_to_file(cache_path)

            logger.info(
                f"TTS generated: {cache_key} (language={language.value}, "
                f"voice={voice}, text_length={len(text)})"
            )

            return cache_path

        except Exception as e:
            logger.error(f"Error generating TTS: {e}", exc_info=True)
            return None


# Global service instance
tts_service = TTSService()
```

#### Интеграция в handlers.py

```python
# Добавить в handle_question_selection():

# After getting the question text
question = items[index]

# Generate voice version if enabled
if settings.enable_tts:
    audio_path = await tts_service.text_to_speech(question, session.language)
    if audio_path:
        # Send audio along with image
        await query.message.reply_audio(
            audio=open(audio_path, 'rb'),
            caption=get_text('question.audio_caption', session.language)
        )
```

#### Стоимость
- **Стоимость:** $15 за 1 миллион символов (TTS API)
- **Средняя длина вопроса:** 100 символов
- **Стоимость на вопрос:** ~$0.0015
- **Кеширование:** Значительно снижает стоимость при повторных запросах

---

### 3. 📊 Система аналитики и персонализации (ПРИОРИТЕТ: СРЕДНИЙ)

#### Описание
Добавить сбор аналитических данных о поведении пользователей для улучшения игры и персонализации контента.

#### Что отслеживать

```python
# vechnost_bot/analytics.py
"""Analytics service for user behavior tracking."""

from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .payments.database import get_db
from .payments.models import Base, User
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column


class UserAction(Base):
    """Model for tracking user actions."""

    __tablename__ = "user_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    theme: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    question_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


class AnalyticsService:
    """Service for analytics and personalization."""

    @staticmethod
    async def track_action(
        telegram_user_id: int,
        action_type: str,
        **metadata
    ) -> None:
        """Track user action."""
        async with get_db() as session:
            action = UserAction(
                telegram_user_id=telegram_user_id,
                action_type=action_type,
                theme=metadata.get('theme'),
                level=metadata.get('level'),
                question_index=metadata.get('question_index'),
                content_type=metadata.get('content_type'),
                duration_seconds=metadata.get('duration'),
            )
            session.add(action)
            await session.commit()

    @staticmethod
    async def get_popular_themes() -> Dict[str, int]:
        """Get most popular themes."""
        async with get_db() as session:
            result = await session.execute(
                select(
                    UserAction.theme,
                    func.count(UserAction.id).label('count')
                )
                .where(UserAction.theme.isnot(None))
                .group_by(UserAction.theme)
                .order_by(func.count(UserAction.id).desc())
            )
            return {row.theme: row.count for row in result}

    @staticmethod
    async def get_user_favorite_theme(telegram_user_id: int) -> Optional[str]:
        """Get user's most used theme."""
        async with get_db() as session:
            result = await session.execute(
                select(
                    UserAction.theme,
                    func.count(UserAction.id).label('count')
                )
                .where(UserAction.telegram_user_id == telegram_user_id)
                .where(UserAction.theme.isnot(None))
                .group_by(UserAction.theme)
                .order_by(func.count(UserAction.id).desc())
                .limit(1)
            )
            row = result.first()
            return row.theme if row else None


# Usage in handlers:
await AnalyticsService.track_action(
    telegram_user_id=user_id,
    action_type="question_viewed",
    theme=session.theme.value,
    level=session.level,
    question_index=index,
)
```

---

### 4. 🎮 Групповые игровые сессии (ПРИОРИТЕТ: НИЗКИЙ)

#### Описание
Разрешить нескольким пользователям играть вместе в одной сессии через группу или канал.

#### Функциональность
- Создание групповой сессии
- Приглашение участников через ссылку
- Синхронизация карточек для всех участников
- Очередность ответов
- Групповая статистика

---

### 5. 🏆 Геймификация и достижения (ПРИОРИТЕТ: НИЗКИЙ)

#### Описание
Добавить систему достижений, бейджей и прогресса для мотивации пользователей.

#### Примеры достижений
- 🎯 "Первый шаг" - Ответил на 10 вопросов
- 💑 "Влюбленные" - Прошел все уровни темы "Для пар"
- 🔥 "Страстный" - Прошел тему "Секс"
- 📅 "Постоянный игрок" - Играл 7 дней подряд
- 🌟 "Полиглот" - Использовал все 3 языка

---

### 6. 🔔 Система напоминаний (ПРИОРИТЕТ: НИЗКИЙ)

#### Описание
Периодические уведомления для поддержания вовлеченности пользователей.

#### Типы напоминаний
- Ежедневный вопрос дня
- Напоминание о незавершенной теме
- Новые карточки/темы
- Персонализированные рекомендации

---

### 7. 🤖 Интеграция с ChatGPT для генерации кастомных вопросов (ПРИОРИТЕТ: СРЕДНИЙ)

#### Описание
Позволить пользователям генерировать собственные вопросы на основе их предпочтений через ChatGPT API.

```python
# vechnost_bot/question_generator.py
"""Custom question generator using ChatGPT."""

from openai import AsyncOpenAI
from .config import settings
from .i18n import Language


class QuestionGenerator:
    """Generate custom questions using ChatGPT."""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def generate_questions(
        self,
        theme: str,
        level: int,
        language: Language,
        count: int = 5,
    ) -> list[str]:
        """Generate custom questions."""

        prompts = {
            Language.RUSSIAN: f"Сгенерируй {count} интересных вопросов для игры между парой на тему '{theme}', уровень интимности {level}/3.",
            Language.ENGLISH: f"Generate {count} interesting questions for a couple's game on the theme '{theme}', intimacy level {level}/3.",
            Language.CZECH: f"Vygeneruj {count} zajímavých otázek pro hru pro páry na téma '{theme}', úroveň intimity {level}/3.",
        }

        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a relationship coach creating meaningful questions for couples."
                },
                {
                    "role": "user",
                    "content": prompts[language]
                }
            ],
            temperature=0.9,
            max_tokens=500,
        )

        # Parse questions from response
        content = response.choices[0].message.content
        questions = [q.strip() for q in content.split('\n') if q.strip() and not q.strip().startswith('#')]

        return questions[:count]
```

---

## 🔧 Технические улучшения

### 1. Кеширование игрового контента

```python
# vechnost_bot/cache_manager.py
"""Cache manager for frequently accessed data."""

from functools import lru_cache
import redis.asyncio as redis
from typing import Optional, Any
import json
import pickle

class CacheManager:
    """Unified cache manager."""

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.local_cache: dict = {}

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        # Try Redis first
        if self.redis_client:
            value = await self.redis_client.get(key)
            if value:
                return pickle.loads(value)

        # Fallback to local cache
        return self.local_cache.get(key)

    async def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        """Set value in cache."""
        if self.redis_client:
            await self.redis_client.setex(
                key, ttl, pickle.dumps(value)
            )
        else:
            self.local_cache[key] = value
```

### 2. Rate Limiting для команд бота

```python
# vechnost_bot/rate_limiter.py - улучшить существующий
"""Enhanced rate limiter for bot commands."""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Tuple

class BotRateLimiter:
    """Rate limiter for bot commands."""

    def __init__(self):
        self.user_commands: Dict[int, list[datetime]] = defaultdict(list)
        self.limits = {
            'default': (10, 60),  # 10 commands per 60 seconds
            'start': (3, 60),     # 3 starts per 60 seconds
            'voice': (5, 60),     # 5 voice messages per 60 seconds
        }

    def is_allowed(
        self,
        user_id: int,
        command: str = 'default'
    ) -> Tuple[bool, int]:
        """
        Check if user is allowed to execute command.

        Returns:
            (is_allowed, seconds_to_wait)
        """
        limit, window = self.limits.get(command, self.limits['default'])
        now = datetime.now()
        cutoff = now - timedelta(seconds=window)

        # Clean old timestamps
        self.user_commands[user_id] = [
            ts for ts in self.user_commands[user_id]
            if ts > cutoff
        ]

        # Check limit
        if len(self.user_commands[user_id]) >= limit:
            oldest = self.user_commands[user_id][0]
            wait_time = int((oldest + timedelta(seconds=window) - now).total_seconds())
            return False, wait_time

        # Allow and record
        self.user_commands[user_id].append(now)
        return True, 0


# Apply to handlers:
bot_rate_limiter = BotRateLimiter()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    allowed, wait_time = bot_rate_limiter.is_allowed(user_id, 'start')
    if not allowed:
        await update.message.reply_text(
            f"⏱️ Пожалуйста, подождите {wait_time} секунд перед следующей командой."
        )
        return

    # ... rest of handler
```

### 3. Prometheus метрики

```python
# vechnost_bot/metrics.py
"""Prometheus metrics for monitoring."""

from prometheus_client import Counter, Histogram, Gauge, start_http_server

# Metrics
commands_total = Counter(
    'bot_commands_total',
    'Total number of bot commands',
    ['command', 'user_id']
)

voice_messages_total = Counter(
    'bot_voice_messages_total',
    'Total number of voice messages transcribed',
    ['language', 'status']
)

transcription_duration = Histogram(
    'bot_transcription_duration_seconds',
    'Time spent transcribing voice messages'
)

active_sessions = Gauge(
    'bot_active_sessions',
    'Number of active user sessions'
)

# Start metrics server
def start_metrics_server(port: int = 9090) -> None:
    """Start Prometheus metrics HTTP server."""
    start_http_server(port)
```

---

## 📋 Приоритеты реализации

### Высокий приоритет (1-2 недели)
1. ✅ **OpenAI Whisper интеграция** - Голосовой ввод
2. ✅ **Rate Limiting улучшение** - Защита от спама
3. ✅ **Кеширование** - Производительность

### Средний приоритет (2-4 недели)
4. ⚠️ **OpenAI TTS** - Озвучивание вопросов
5. ⚠️ **Аналитика и персонализация** - Улучшение UX
6. ⚠️ **ChatGPT кастомные вопросы** - Генерация контента

### Низкий приоритет (1-3 месяца)
7. 📅 **Групповые сессии** - Социальная функция
8. 📅 **Геймификация** - Мотивация пользователей
9. 📅 **Система напоминаний** - Удержание пользователей

---

## 💰 Оценка стоимости OpenAI API

### Месячная оценка (1000 активных пользователей)

| Функция | Использование | Стоимость за единицу | Месячная стоимость |
|---------|--------------|---------------------|-------------------|
| **Whisper (транскрипция)** | 2 голосовых в день × 20 сек | $0.006/мин | ~$24/месяц |
| **TTS (озвучка)** | 5 вопросов в день × 100 символов | $15/1M символов | ~$2.25/месяц |
| **ChatGPT (генерация)** | 10 запросов в месяц | $0.15/1M токенов | ~$4.50/месяц |
| **ИТОГО** | | | **~$31/месяц** |

**При 10,000 пользователей:** ~$310/месяц
**ROI:** Если средний чек подписки $5/месяц, окупается с 62 платящих пользователей

---

## 🎯 Заключение

Проект **Vechnost Bot** имеет отличную архитектурную основу и готов к масштабированию. Основные рекомендации:

### Немедленные действия (эта неделя)
1. ✅ Добавить OpenAI Whisper для голосового ввода
2. ✅ Улучшить rate limiting для всех команд
3. ✅ Добавить кеширование игрового контента

### Краткосрочные цели (этот месяц)
1. ⚠️ Реализовать систему аналитики
2. ⚠️ Добавить TTS для озвучивания вопросов
3. ⚠️ Настроить Prometheus метрики

### Долгосрочные цели (квартал)
1. 📅 Групповые игровые сессии
2. 📅 Система достижений
3. 📅 Кастомная генерация вопросов через GPT

---

**Автор анализа:** AI Assistant with Context7
**Контакт:** Для вопросов обращайтесь к команде разработки
**Лицензия:** MIT

