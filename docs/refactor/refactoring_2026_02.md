# 🔄 Vechnost Bot - План рефакторинга и развития
## Февраль 2026

**Дата анализа:** 3 февраля 2026  
**Версия проекта:** 1.0.0  
**Проанализировано:** 38 Python модулей, 6 YAML файлов, система платежей, графический рендеринг  

---

## 📊 Содержание

1. [Резюме](#резюме)
2. [Интеграция с ИИ](#-интеграция-с-искусственным-интеллектом)
3. [Графическая часть](#-улучшение-графической-части)
4. [24-часовой бесплатный доступ](#-24-часовой-бесплатный-доступ)
5. [Игровые улучшения](#-игровые-улучшения-и-вовлечённость)
6. [Монетизация](#-стратегия-монетизации)
7. [Технический план](#-технический-план-реализации)
8. [Приложения](#-приложения)

---

## Резюме

### Текущее состояние проекта

Vechnost Bot — это production-ready Telegram бот для карточной игры, направленной на углубление отношений. Проект имеет **отличную архитектурную основу**:

| Компонент | Статус | Оценка |
|-----------|--------|--------|
| Clean Architecture | ✅ Реализовано | 9/10 |
| Платежная система (Tribute) | ✅ Работает | 8/10 |
| Многоязычность (RU/EN/CS) | ✅ Полная | 9/10 |
| Рендеринг карточек | ✅ Базовый | 6/10 |
| AI интеграция | ❌ Отсутствует | 0/10 |
| Аналитика | ⚠️ Минимальная | 3/10 |
| Геймификация | ❌ Отсутствует | 0/10 |

### Ключевые направления развития

```
┌─────────────────────────────────────────────────────────────────┐
│                    VECHNOST ROADMAP 2026                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Q1 2026                                                        │
│  ├── 🤖 AI Integration (Whisper + GPT)                          │
│  ├── 🎨 Enhanced Graphics                                       │
│  └── 🎁 24h Free Trial System                                   │
│                                                                 │
│  Q2 2026                                                        │
│  ├── 🎮 Gamification & Achievements                             │
│  ├── 👥 Group Sessions                                          │
│  └── 📊 Advanced Analytics                                      │
│                                                                 │
│  Q3-Q4 2026                                                     │
│  ├── 💎 Premium Features                                        │
│  ├── 🌍 New Languages                                           │
│  └── 📱 Mini App Integration                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🤖 Интеграция с искусственным интеллектом

### 1. OpenAI Whisper — Голосовой ввод

**Приоритет:** 🔴 ВЫСОКИЙ  
**Сложность:** Средняя  
**Время реализации:** 3-5 дней  
**Стоимость API:** ~$0.006/минута (~$30/месяц на 1000 пользователей)

#### Концепция

Пользователи смогут отвечать на вопросы голосом, что создаёт более интимную и естественную атмосферу общения. Особенно ценно для тем "Для пар" и "Секс", где текстовый ввод может быть неловким.

#### Архитектура решения

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Telegram      │────▶│  Voice Handler   │────▶│  OpenAI        │
│   Voice Msg     │     │  (download .ogg) │     │  Whisper API   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                          │
                                                          ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Response      │◀────│  Session State   │◀────│  Transcribed   │
│   to User       │     │  Update          │     │  Text          │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

#### Реализация

```python
# vechnost_bot/ai/whisper_service.py
"""Voice transcription service using OpenAI Whisper API."""

import logging
from pathlib import Path
from typing import Optional
import aiofiles
from openai import AsyncOpenAI

from ..config import settings
from ..i18n import Language
from ..monitoring import track_performance, log_bot_event

logger = logging.getLogger(__name__)


class WhisperService:
    """Service for transcribing voice messages using OpenAI Whisper."""

    # Language mapping for Whisper API
    LANGUAGE_MAP = {
        Language.RUSSIAN: "ru",
        Language.ENGLISH: "en",
        Language.CZECH: "cs",
    }

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.temp_dir = Path("temp/voice")
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    @track_performance("transcribe_voice")
    async def transcribe(
        self,
        audio_data: bytes,
        language: Language,
        user_id: int,
    ) -> Optional[str]:
        """
        Transcribe audio bytes to text.

        Args:
            audio_data: Raw audio bytes (OGG format from Telegram)
            language: Preferred language for transcription
            user_id: User ID for logging

        Returns:
            Transcribed text or None if error
        """
        try:
            transcription = await self.client.audio.transcriptions.create(
                model="whisper-1",
                file=("audio.ogg", audio_data, "audio/ogg"),
                response_format="verbose_json",
                language=self.LANGUAGE_MAP.get(language, "ru"),
                temperature=0.0,  # More deterministic output
            )

            text = transcription.text.strip()
            
            log_bot_event(
                "voice_transcribed",
                user_id=user_id,
                text_length=len(text),
                detected_language=transcription.language,
                duration=transcription.duration,
            )

            logger.info(
                f"Voice transcribed for user {user_id}: "
                f"{len(text)} chars, {transcription.duration:.1f}s"
            )

            return text

        except Exception as e:
            logger.error(f"Whisper transcription error: {e}", exc_info=True)
            log_bot_event("voice_transcription_error", user_id=user_id, error=str(e))
            return None


# Singleton instance
whisper_service = WhisperService()
```

#### Интеграция с хендлерами

```python
# vechnost_bot/handlers.py — добавить обработчик голосовых сообщений

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from .ai.whisper_service import whisper_service


async def handle_voice_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle incoming voice messages."""
    if not update.message or not update.message.voice:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # Get session for language preference
    session = await get_session(chat_id)
    language = session.language

    # Show typing indicator
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # Download voice file
    voice = update.message.voice
    voice_file = await context.bot.get_file(voice.file_id)
    audio_bytes = await voice_file.download_as_bytearray()

    # Transcribe
    text = await whisper_service.transcribe(
        audio_data=bytes(audio_bytes),
        language=language,
        user_id=user_id,
    )

    if text:
        response = get_text("voice.transcribed", language).format(text=text)
        await update.message.reply_text(response, parse_mode="HTML")
    else:
        error_msg = get_text("voice.error", language)
        await update.message.reply_text(error_msg)


# Register in bot.py:
# application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
```

#### Переводы

```yaml
# data/translations_ru.yaml
voice:
  processing: "🎤 Распознаю голосовое сообщение..."
  transcribed: "📝 <b>Вы сказали:</b>\n\n<i>{text}</i>"
  error: "❌ Не удалось распознать голос. Попробуйте ещё раз или отправьте текстом."
  too_long: "⏱️ Голосовое сообщение слишком длинное (максимум 2 минуты)"

# data/translations_en.yaml  
voice:
  processing: "🎤 Transcribing voice message..."
  transcribed: "📝 <b>You said:</b>\n\n<i>{text}</i>"
  error: "❌ Failed to transcribe. Please try again or send as text."
  too_long: "⏱️ Voice message too long (max 2 minutes)"

# data/translations_cs.yaml
voice:
  processing: "🎤 Přepisuji hlasovou zprávu..."
  transcribed: "📝 <b>Řekli jste:</b>\n\n<i>{text}</i>"
  error: "❌ Nepodařilo se přepsat. Zkuste znovu nebo pošlete text."
  too_long: "⏱️ Hlasová zpráva je příliš dlouhá (max 2 minuty)"
```

---

### 2. ChatGPT — Персонализированные вопросы

**Приоритет:** 🟡 СРЕДНИЙ  
**Сложность:** Средняя  
**Время реализации:** 5-7 дней  
**Стоимость API:** ~$0.15/1M токенов (~$5/месяц на 1000 пользователей)

#### Концепция

AI генерирует персонализированные вопросы на основе:
- Контекста пары (давно вместе / только познакомились)
- Предпочтений и истории игры
- Специфических запросов пользователя

#### Архитектура

```python
# vechnost_bot/ai/question_generator.py
"""AI-powered custom question generator."""

from typing import Optional
from openai import AsyncOpenAI

from ..config import settings
from ..i18n import Language
from ..models import Theme


class QuestionGenerator:
    """Generate personalized questions using GPT-4o-mini."""

    SYSTEM_PROMPTS = {
        Language.RUSSIAN: """Ты — создатель глубоких и интимных вопросов для пар. 
Твоя задача — генерировать вопросы, которые:
- Помогают партнёрам узнать друг друга глубже
- Соответствуют указанному уровню интимности
- Вызывают искренние и честные разговоры
- НЕ являются клишированными или банальными

Формат ответа: только вопросы, каждый с новой строки, без нумерации.""",

        Language.ENGLISH: """You are a creator of deep and intimate questions for couples.
Your task is to generate questions that:
- Help partners know each other deeper
- Match the specified intimacy level
- Spark sincere and honest conversations
- Are NOT clichéd or banal

Response format: questions only, one per line, no numbering.""",

        Language.CZECH: """Jsi tvůrce hlubokých a intimních otázek pro páry.
Tvým úkolem je generovat otázky, které:
- Pomohou partnerům lépe se poznat
- Odpovídají uvedené úrovni intimity
- Vyvolávají upřímné a čestné rozhovory
- NEJSOU klišé nebo banální

Formát odpovědi: pouze otázky, každá na novém řádku, bez číslování.""",
    }

    THEME_CONTEXTS = {
        Theme.ACQUAINTANCE: "первое знакомство, лёгкий флирт, узнавание нового человека",
        Theme.FOR_COUPLES: "глубокие отношения, общие ценности, будущее вместе",
        Theme.SEX: "интимная близость, желания, фантазии, сексуальная совместимость",
        Theme.PROVOCATION: "провокационные темы, сложные выборы, моральные дилеммы",
    }

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def generate_questions(
        self,
        theme: Theme,
        level: int,
        language: Language,
        context: Optional[str] = None,
        count: int = 5,
    ) -> list[str]:
        """
        Generate personalized questions.

        Args:
            theme: Game theme
            level: Intimacy level (1-3)
            language: Target language
            context: Optional user context (e.g., "together 5 years")
            count: Number of questions to generate

        Returns:
            List of generated questions
        """
        theme_context = self.THEME_CONTEXTS.get(theme, "общение между партнёрами")
        
        user_prompt = f"""Сгенерируй {count} уникальных вопросов.

Тема: {theme.value}
Контекст темы: {theme_context}
Уровень интимности: {level}/3 (где 1 — легкий, 3 — глубокий)
"""
        if context:
            user_prompt += f"\nКонтекст пары: {context}"

        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPTS[language]},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.9,  # Higher creativity
            max_tokens=1000,
        )

        content = response.choices[0].message.content
        questions = [
            q.strip().lstrip("0123456789.-) ")
            for q in content.split("\n")
            if q.strip() and len(q.strip()) > 10
        ]

        return questions[:count]


# Singleton
question_generator = QuestionGenerator()
```

#### UI для генерации

```python
# Добавить в keyboards.py

def get_ai_question_keyboard(language: Language) -> InlineKeyboardMarkup:
    """Get keyboard for AI question generation."""
    keyboard = [
        [InlineKeyboardButton(
            "✨ " + get_text('ai.generate_question', language),
            callback_data="ai:generate"
        )],
        [InlineKeyboardButton(
            get_text('navigation.back', language),
            callback_data="back:themes"
        )],
    ]
    return InlineKeyboardMarkup(keyboard)
```

---

### 3. OpenAI TTS — Озвучивание вопросов

**Приоритет:** 🟢 НИЗКИЙ  
**Сложность:** Низкая  
**Время реализации:** 2-3 дня  
**Стоимость API:** ~$15/1M символов (~$3/месяц на 1000 пользователей)

#### Концепция

Вопросы из карточек озвучиваются голосом, создавая атмосферу "игрового мастера". Особенно полезно для:
- Создания атмосферы
- Пользователей с ограничениями зрения
- Игры в темноте / романтической обстановке

```python
# vechnost_bot/ai/tts_service.py
"""Text-to-Speech service using OpenAI TTS API."""

import hashlib
from pathlib import Path
from typing import Optional
from openai import AsyncOpenAI

from ..config import settings
from ..i18n import Language


class TTSService:
    """Convert text to speech with caching."""

    VOICE_MAP = {
        Language.RUSSIAN: "nova",   # Soft female voice
        Language.ENGLISH: "alloy",  # Neutral voice
        Language.CZECH: "shimmer",  # Warm female voice
    }

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.cache_dir = Path("cache/tts")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, text: str, language: Language) -> str:
        """Generate cache key for audio."""
        content = f"{text}:{language.value}".encode('utf-8')
        return hashlib.sha256(content).hexdigest()[:16]

    async def text_to_speech(
        self,
        text: str,
        language: Language,
    ) -> Optional[Path]:
        """
        Convert text to speech audio file.

        Args:
            text: Text to convert
            language: Voice language

        Returns:
            Path to MP3 file or None if error
        """
        cache_key = self._cache_key(text, language)
        cache_path = self.cache_dir / f"{cache_key}.mp3"

        # Return cached if exists
        if cache_path.exists():
            return cache_path

        try:
            voice = self.VOICE_MAP.get(language, "nova")
            
            response = await self.client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=text[:4096],  # API limit
                response_format="mp3",
            )

            response.stream_to_file(cache_path)
            return cache_path

        except Exception as e:
            logger.error(f"TTS error: {e}")
            return None


tts_service = TTSService()
```

---

## 🎨 Улучшение графической части

### Текущее состояние

Рендеринг карточек (`renderer.py`) использует:
- PIL/Pillow для рендеринга
- Фиксированный размер 1080x1350
- Один шрифт (DejaVuSans, 53px)
- Базовые фоны для каждой темы

### Проблемы

1. **Однообразный дизайн** — все карточки выглядят одинаково
2. **Нет адаптации текста** — длинные вопросы плохо читаются
3. **Отсутствие анимаций** — статичные изображения
4. **Нет брендирования** — отсутствует логотип на карточках

### План улучшений

#### 1. Динамический дизайн карточек

```python
# vechnost_bot/renderer_v2.py
"""Enhanced card renderer with dynamic design."""

from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO
from typing import Optional
import colorsys


@dataclass
class CardStyle:
    """Style configuration for card rendering."""
    primary_color: tuple[int, int, int]
    secondary_color: tuple[int, int, int]
    text_color: tuple[int, int, int]
    font_family: str
    corner_radius: int = 40
    shadow_blur: int = 20
    gradient_angle: int = 135


class ThemeStyles:
    """Theme-specific styles."""
    
    ACQUAINTANCE = CardStyle(
        primary_color=(255, 215, 0),    # Gold
        secondary_color=(255, 193, 7),  # Amber
        text_color=(33, 33, 33),        # Dark gray
        font_family="Montserrat-Medium",
    )
    
    FOR_COUPLES = CardStyle(
        primary_color=(233, 30, 99),    # Pink
        secondary_color=(156, 39, 176), # Purple
        text_color=(255, 255, 255),     # White
        font_family="Playfair-Regular",
    )
    
    SEX = CardStyle(
        primary_color=(244, 67, 54),    # Red
        secondary_color=(183, 28, 28),  # Dark red
        text_color=(255, 255, 255),     # White
        font_family="Roboto-Bold",
    )
    
    PROVOCATION = CardStyle(
        primary_color=(103, 58, 183),   # Deep purple
        secondary_color=(63, 81, 181),  # Indigo
        text_color=(255, 255, 255),     # White
        font_family="Oswald-Regular",
    )


class EnhancedRenderer:
    """Enhanced card renderer with modern design."""

    def __init__(self):
        self.width = 1080
        self.height = 1350
        self.logo_path = Path("assets/images/vechnost_logo.png")

    def _create_gradient_background(
        self,
        style: CardStyle,
        level: int,
    ) -> Image.Image:
        """Create gradient background based on theme and level."""
        img = Image.new('RGB', (self.width, self.height))
        draw = ImageDraw.Draw(img)

        # Adjust colors based on level (darker = deeper level)
        factor = 1 - (level - 1) * 0.15
        
        def adjust_brightness(color: tuple, f: float) -> tuple:
            return tuple(int(c * f) for c in color)

        c1 = adjust_brightness(style.primary_color, factor)
        c2 = adjust_brightness(style.secondary_color, factor)

        # Create smooth gradient
        for y in range(self.height):
            ratio = y / self.height
            r = int(c1[0] * (1 - ratio) + c2[0] * ratio)
            g = int(c1[1] * (1 - ratio) + c2[1] * ratio)
            b = int(c1[2] * (1 - ratio) + c2[2] * ratio)
            draw.line([(0, y), (self.width, y)], fill=(r, g, b))

        return img

    def _add_decorative_elements(
        self,
        img: Image.Image,
        style: CardStyle,
        question_number: int,
    ) -> Image.Image:
        """Add decorative elements to the card."""
        draw = ImageDraw.Draw(img)

        # Add subtle pattern overlay
        # Add corner decorations
        # Add question number badge
        
        # Number badge in top-right
        badge_size = 80
        badge_x = self.width - badge_size - 40
        badge_y = 40
        
        draw.ellipse(
            [badge_x, badge_y, badge_x + badge_size, badge_y + badge_size],
            fill=(255, 255, 255, 180)
        )
        
        # Draw number
        font = ImageFont.truetype("assets/fonts/Montserrat-Bold.ttf", 36)
        number_text = str(question_number)
        bbox = font.getbbox(number_text)
        text_x = badge_x + (badge_size - (bbox[2] - bbox[0])) // 2
        text_y = badge_y + (badge_size - (bbox[3] - bbox[1])) // 2
        draw.text((text_x, text_y), number_text, fill=style.primary_color, font=font)

        return img

    def _add_logo_watermark(self, img: Image.Image) -> Image.Image:
        """Add subtle logo watermark."""
        if not self.logo_path.exists():
            return img

        logo = Image.open(self.logo_path).convert('RGBA')
        
        # Scale logo to 100px width
        ratio = 100 / logo.width
        logo = logo.resize(
            (100, int(logo.height * ratio)),
            Image.Resampling.LANCZOS
        )

        # Make semi-transparent
        logo.putalpha(int(255 * 0.3))

        # Position in bottom-right
        x = self.width - logo.width - 30
        y = self.height - logo.height - 30

        img.paste(logo, (x, y), logo)
        return img

    def render_card(
        self,
        text: str,
        theme: str,
        level: int,
        question_number: int,
        total_questions: int,
    ) -> BytesIO:
        """
        Render a question card with enhanced design.

        Args:
            text: Question text
            theme: Theme name
            level: Level number (1-3)
            question_number: Current question number
            total_questions: Total questions in category

        Returns:
            BytesIO with JPEG image data
        """
        # Get theme style
        style_map = {
            "Acquaintance": ThemeStyles.ACQUAINTANCE,
            "For Couples": ThemeStyles.FOR_COUPLES,
            "Sex": ThemeStyles.SEX,
            "Provocation": ThemeStyles.PROVOCATION,
        }
        style = style_map.get(theme, ThemeStyles.ACQUAINTANCE)

        # Create base image
        img = self._create_gradient_background(style, level)
        img = self._add_decorative_elements(img, style, question_number)
        
        # Add text
        img = self._render_text(img, text, style)
        
        # Add watermark
        img = self._add_logo_watermark(img)

        # Export
        output = BytesIO()
        img.save(output, format='JPEG', quality=92, optimize=True)
        output.seek(0)
        return output
```

#### 2. Анимированные карточки (GIF)

```python
# vechnost_bot/animated_renderer.py
"""Animated card renderer for special effects."""

from PIL import Image
from io import BytesIO


class AnimatedRenderer:
    """Create animated GIF cards for special moments."""

    def render_reveal_animation(
        self,
        question: str,
        theme: str,
        frames: int = 15,
        duration: int = 50,  # ms per frame
    ) -> BytesIO:
        """
        Create card reveal animation.
        
        The card appears to flip/reveal from blank to question.
        """
        images = []
        
        for i in range(frames):
            progress = i / (frames - 1)  # 0.0 to 1.0
            
            # First half: show back of card
            if progress < 0.5:
                img = self._render_card_back(theme, progress * 2)
            else:
                # Second half: reveal question with fade-in
                opacity = (progress - 0.5) * 2
                img = self._render_card_front(question, theme, opacity)
            
            images.append(img)

        output = BytesIO()
        images[0].save(
            output,
            format='GIF',
            save_all=True,
            append_images=images[1:],
            duration=duration,
            loop=0,
        )
        output.seek(0)
        return output
```

#### 3. Responsive текст

```python
def _calculate_optimal_font_size(
    self,
    text: str,
    max_width: int,
    max_height: int,
    min_size: int = 32,
    max_size: int = 64,
) -> tuple[ImageFont.FreeTypeFont, int]:
    """
    Calculate optimal font size for text to fit in bounds.
    
    Returns:
        (font, optimal_size)
    """
    for size in range(max_size, min_size - 1, -2):
        font = ImageFont.truetype(self.font_path, size)
        lines = self._wrap_text(text, font, max_width)
        
        total_height = sum(
            font.getbbox(line)[3] - font.getbbox(line)[1]
            for line in lines
        ) + (len(lines) - 1) * int(size * 0.4)  # line spacing
        
        if total_height <= max_height:
            return font, size
    
    return ImageFont.truetype(self.font_path, min_size), min_size
```

---

## 🎁 24-часовой бесплатный доступ

### Концепция

Дать новым пользователям **полный доступ на 24 часа** без оплаты. Это позволит:
- Попробовать все функции игры
- Сформировать привычку использования
- Принять решение о покупке на основе опыта

### Архитектура решения

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   New User      │────▶│  Create Trial    │────▶│  trial_access   │
│   /start        │     │  Session         │     │  table in DB    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                          │
                                                          ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   24h Passed    │◀────│  Middleware      │◀────│  Check expiry   │
│   Show Paywall  │     │  Check Access    │     │  on each cmd    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

### Реализация

#### Модель данных

```python
# vechnost_bot/payments/models.py — добавить модель

class TrialAccess(Base):
    """Model for tracking free trial access."""

    __tablename__ = "trial_access"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    converted_to_paid: Mapped[bool] = mapped_column(default=False, nullable=False)
    reminder_sent: Mapped[bool] = mapped_column(default=False, nullable=False)

    __table_args__ = (
        Index("idx_trial_telegram_user", "telegram_user_id"),
        Index("idx_trial_expires", "expires_at"),
    )

    @property
    def is_active(self) -> bool:
        """Check if trial is still active."""
        return datetime.utcnow() < self.expires_at

    @property
    def hours_remaining(self) -> int:
        """Get hours remaining in trial."""
        if not self.is_active:
            return 0
        delta = self.expires_at - datetime.utcnow()
        return int(delta.total_seconds() / 3600)
```

#### Сервис триала

```python
# vechnost_bot/payments/trial_service.py
"""Service for managing free trial access."""

from datetime import datetime, timedelta
from typing import Optional
import logging

from .database import get_db
from .models import TrialAccess
from .repositories import TrialRepository

logger = logging.getLogger(__name__)

TRIAL_DURATION_HOURS = 24


class TrialService:
    """Service for free trial management."""

    @staticmethod
    async def start_trial(telegram_user_id: int) -> TrialAccess:
        """
        Start a new trial for user.
        
        Args:
            telegram_user_id: Telegram user ID
            
        Returns:
            TrialAccess instance
        """
        async with get_db() as session:
            # Check if trial already exists
            existing = await TrialRepository.get_by_telegram_id(
                session, telegram_user_id
            )
            
            if existing:
                logger.info(
                    f"User {telegram_user_id} already has trial "
                    f"(expires: {existing.expires_at})"
                )
                return existing
            
            # Create new trial
            trial = await TrialRepository.create(
                session,
                telegram_user_id=telegram_user_id,
                expires_at=datetime.utcnow() + timedelta(hours=TRIAL_DURATION_HOURS),
            )
            
            logger.info(
                f"Trial started for user {telegram_user_id}, "
                f"expires at {trial.expires_at}"
            )
            
            return trial

    @staticmethod
    async def check_trial_access(telegram_user_id: int) -> tuple[bool, Optional[int]]:
        """
        Check if user has active trial access.
        
        Returns:
            (has_access, hours_remaining)
        """
        async with get_db() as session:
            trial = await TrialRepository.get_by_telegram_id(
                session, telegram_user_id
            )
            
            if not trial:
                return False, None
            
            if trial.is_active:
                return True, trial.hours_remaining
            
            return False, 0

    @staticmethod
    async def send_expiration_reminder(telegram_user_id: int) -> bool:
        """
        Mark reminder as sent for expiring trial.
        
        Returns:
            True if reminder should be sent (wasn't sent before)
        """
        async with get_db() as session:
            trial = await TrialRepository.get_by_telegram_id(
                session, telegram_user_id
            )
            
            if not trial or trial.reminder_sent:
                return False
            
            # Check if 2 hours remaining
            if trial.hours_remaining <= 2 and trial.hours_remaining > 0:
                await TrialRepository.mark_reminder_sent(session, trial)
                return True
            
            return False


trial_service = TrialService()
```

#### Интеграция в middleware

```python
# vechnost_bot/payments/middleware.py — обновить

async def check_payment_or_trial(telegram_user_id: int) -> tuple[bool, str]:
    """
    Check if user has paid access OR active trial.
    
    Returns:
        (has_access, access_type)  # access_type: "paid", "trial", "none"
    """
    # Check paid access first
    if await user_has_access(telegram_user_id):
        return True, "paid"
    
    # Check trial access
    has_trial, hours_left = await trial_service.check_trial_access(telegram_user_id)
    if has_trial:
        return True, "trial"
    
    return False, "none"
```

#### UI для триала

```python
# Показать статус триала в welcome message

async def show_trial_status(
    update: Update,
    trial: TrialAccess,
    language: Language,
) -> None:
    """Show trial status banner."""
    hours = trial.hours_remaining
    
    if hours > 6:
        emoji = "🎁"
        urgency = ""
    elif hours > 2:
        emoji = "⏰"
        urgency = get_text("trial.ending_soon", language)
    else:
        emoji = "⚠️"
        urgency = get_text("trial.ending_very_soon", language)
    
    status_text = get_text("trial.status", language).format(
        emoji=emoji,
        hours=hours,
        urgency=urgency,
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            get_text("trial.upgrade_now", language),
            url=settings.tribute_payment_url
        )]
    ])
    
    await update.message.reply_text(
        status_text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )
```

#### Переводы

```yaml
# data/translations_ru.yaml
trial:
  welcome: |
    🎁 <b>Добро пожаловать!</b>
    
    У вас есть <b>24 часа бесплатного доступа</b> ко всем функциям игры.
    
    Используйте это время, чтобы исследовать все темы и найти свою любимую!
  
  status: "{emoji} Осталось <b>{hours}ч</b> бесплатного доступа {urgency}"
  ending_soon: "— успейте попробовать всё!"
  ending_very_soon: "— пора принять решение!"
  
  expired: |
    ⏰ <b>Ваш пробный период закончился</b>
    
    Надеемся, вам понравилась игра!
    
    Приобретите полный доступ, чтобы продолжить открывать новые стороны ваших отношений.
  
  upgrade_now: "💎 Получить полный доступ"
  
  reminder: |
    ⏰ <b>Осталось всего {hours} часа!</b>
    
    Ваш бесплатный доступ скоро закончится.
    
    Хотите продолжить играть? Сейчас самое время получить полный доступ!
```

#### Автоматические напоминания

```python
# vechnost_bot/jobs/trial_reminder.py
"""Background job for trial expiration reminders."""

from telegram import Bot
from datetime import datetime, timedelta

from ..payments.trial_service import trial_service
from ..payments.repositories import TrialRepository
from ..payments.database import get_db
from ..i18n import get_text, Language


async def send_trial_reminders(bot: Bot) -> int:
    """
    Send reminders to users whose trials are expiring soon.
    
    Returns:
        Number of reminders sent
    """
    sent_count = 0
    
    async with get_db() as session:
        # Get trials expiring in next 2 hours that haven't been reminded
        expiring_trials = await TrialRepository.get_expiring_soon(
            session,
            hours_until_expiry=2,
        )
        
        for trial in expiring_trials:
            try:
                # Get user's language preference
                from ..storage import get_session
                user_session = await get_session(trial.telegram_user_id)
                language = user_session.language
                
                # Send reminder
                reminder_text = get_text("trial.reminder", language).format(
                    hours=trial.hours_remaining
                )
                
                await bot.send_message(
                    chat_id=trial.telegram_user_id,
                    text=reminder_text,
                    parse_mode="HTML",
                )
                
                # Mark as sent
                await TrialRepository.mark_reminder_sent(session, trial)
                sent_count += 1
                
            except Exception as e:
                logger.error(
                    f"Failed to send trial reminder to {trial.telegram_user_id}: {e}"
                )
    
    return sent_count


# Register as scheduled job in bot.py:
# application.job_queue.run_repeating(
#     send_trial_reminders,
#     interval=timedelta(minutes=30),
#     first=timedelta(minutes=5),
# )
```

---

## 🎮 Игровые улучшения и вовлечённость

### 1. Система достижений

```python
# vechnost_bot/achievements.py
"""Achievement system for gamification."""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class AchievementType(str, Enum):
    """Types of achievements."""
    FIRST_STEPS = "first_steps"        # Complete 10 questions
    EXPLORER = "explorer"               # Try all themes
    DEEP_DIVER = "deep_diver"          # Complete level 3 of any theme
    PASSIONATE = "passionate"           # Complete Sex theme
    PROVOCATEUR = "provocateur"         # Complete Provocation theme
    POLYGLOT = "polyglot"              # Use all 3 languages
    DAILY_PLAYER = "daily_player"      # Play 7 days in a row
    VOICE_USER = "voice_user"          # Send 10 voice messages
    COUPLE_GOALS = "couple_goals"      # Complete For Couples theme


@dataclass
class Achievement:
    """Achievement definition."""
    type: AchievementType
    name: dict[str, str]  # Localized names
    description: dict[str, str]  # Localized descriptions
    emoji: str
    points: int
    requirement: int  # Required count to unlock


ACHIEVEMENTS = {
    AchievementType.FIRST_STEPS: Achievement(
        type=AchievementType.FIRST_STEPS,
        name={"ru": "Первые шаги", "en": "First Steps", "cs": "První kroky"},
        description={
            "ru": "Ответь на 10 вопросов",
            "en": "Answer 10 questions",
            "cs": "Odpověz na 10 otázek",
        },
        emoji="🎯",
        points=10,
        requirement=10,
    ),
    AchievementType.EXPLORER: Achievement(
        type=AchievementType.EXPLORER,
        name={"ru": "Исследователь", "en": "Explorer", "cs": "Průzkumník"},
        description={
            "ru": "Попробуй все 4 темы",
            "en": "Try all 4 themes",
            "cs": "Vyzkoušej všechny 4 témata",
        },
        emoji="🌟",
        points=25,
        requirement=4,
    ),
    # ... more achievements
}


class AchievementService:
    """Service for tracking and awarding achievements."""

    async def check_and_award(
        self,
        telegram_user_id: int,
        action: str,
        **context
    ) -> Optional[Achievement]:
        """
        Check if user earned an achievement and award it.
        
        Returns:
            Achievement if newly awarded, None otherwise
        """
        # Implementation...
        pass

    async def get_user_achievements(
        self,
        telegram_user_id: int
    ) -> list[Achievement]:
        """Get list of user's earned achievements."""
        pass
```

### 2. Групповые сессии

```python
# vechnost_bot/group_sessions.py
"""Group game session management."""

from dataclasses import dataclass
from typing import Optional
import secrets


@dataclass
class GroupSession:
    """Group game session."""
    session_id: str
    host_user_id: int
    participants: list[int]
    theme: str
    level: int
    current_question_idx: int
    created_at: datetime
    
    @property
    def invite_link(self) -> str:
        """Generate invite deep link."""
        return f"https://t.me/VechnostBot?start=join_{self.session_id}"


class GroupSessionService:
    """Service for managing group sessions."""

    async def create_session(
        self,
        host_user_id: int,
        theme: str,
        level: int,
    ) -> GroupSession:
        """Create a new group session."""
        session_id = secrets.token_urlsafe(8)
        
        session = GroupSession(
            session_id=session_id,
            host_user_id=host_user_id,
            participants=[host_user_id],
            theme=theme,
            level=level,
            current_question_idx=0,
            created_at=datetime.utcnow(),
        )
        
        # Store in Redis with 2 hour TTL
        await self._store_session(session)
        
        return session

    async def join_session(
        self,
        session_id: str,
        user_id: int,
    ) -> Optional[GroupSession]:
        """Join an existing session."""
        session = await self._get_session(session_id)
        
        if not session:
            return None
        
        if user_id not in session.participants:
            session.participants.append(user_id)
            await self._store_session(session)
        
        return session

    async def sync_question(
        self,
        session_id: str,
        question_idx: int,
    ) -> None:
        """Sync question index for all participants."""
        session = await self._get_session(session_id)
        if session:
            session.current_question_idx = question_idx
            await self._store_session(session)
            
            # Notify all participants
            for user_id in session.participants:
                await self._notify_question_change(user_id, question_idx)
```

### 3. Ежедневный вопрос

```python
# vechnost_bot/daily_question.py
"""Daily question feature."""

import random
from datetime import date


class DailyQuestionService:
    """Service for daily question feature."""

    async def get_daily_question(
        self,
        language: Language,
    ) -> tuple[str, str, int]:
        """
        Get today's daily question.
        
        Returns:
            (question_text, theme, level)
        """
        # Use date as seed for consistent daily question
        today = date.today()
        random.seed(today.toordinal())
        
        # Select random theme and question
        themes = list(GAME_DATA.themes.keys())
        theme = random.choice(themes)
        
        level = random.randint(1, 3)
        questions = GAME_DATA.get_content(theme, level, ContentType.QUESTIONS)
        
        if not questions:
            level = None
            questions = GAME_DATA.get_content(theme, None, ContentType.QUESTIONS)
        
        question = random.choice(questions)
        
        return question, theme.value, level

    async def send_daily_question(
        self,
        bot: Bot,
        user_ids: list[int],
    ) -> int:
        """
        Send daily question to subscribed users.
        
        Returns:
            Number of messages sent
        """
        sent = 0
        
        for user_id in user_ids:
            try:
                session = await get_session(user_id)
                question, theme, level = await self.get_daily_question(
                    session.language
                )
                
                text = get_text("daily.question", session.language).format(
                    question=question,
                    theme=theme,
                )
                
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode="HTML",
                )
                sent += 1
                
            except Exception as e:
                logger.error(f"Failed to send daily question to {user_id}: {e}")
        
        return sent
```

---

## 💰 Стратегия монетизации

### Текущая модель

Сейчас используется:
- Tribute API для обработки платежей
- Система сертификатов для бесплатного доступа
- Единоразовая покупка lifetime доступа

### Рекомендуемая ценовая политика

#### Модели монетизации

```
┌─────────────────────────────────────────────────────────────────┐
│                    PRICING TIERS                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  🆓 FREE TRIAL (24 hours)                                       │
│     • Full access to all features                               │
│     • No payment required                                       │
│     • Automatic expiration                                      │
│                                                                 │
│  ⭐ BASIC ($4.99/month or 250 Stars)                           │
│     • All themes and questions                                  │
│     • Card rendering                                            │
│     • Multi-language support                                    │
│                                                                 │
│  💎 PREMIUM ($9.99/month or 500 Stars)                          │
│     • Everything in Basic                                       │
│     • AI voice transcription                                    │
│     • AI-generated custom questions                             │
│     • Voice narration of questions                              │
│     • Priority support                                          │
│                                                                 │
│  👑 LIFETIME ($29.99 or 1500 Stars)                            │
│     • All Premium features forever                              │
│     • Early access to new features                              │
│     • Exclusive themes                                          │
│                                                                 │
│  🎁 GIFT CERTIFICATES ($19.99+)                                │
│     • 1 month / 3 months / Lifetime                            │
│     • Shareable QR codes                                        │
│     • Perfect for couples as gift                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### Telegram Stars Integration

Telegram Stars — новая валюта для оплаты в ботах. Преимущества:
- Нативная интеграция без внешних платёжных систем
- Низкая комиссия (15-30% vs 30% у App Store)
- Мгновенные платежи без верификации
- Подписки с автопродлением

```python
# vechnost_bot/payments/stars_handler.py
"""Telegram Stars payment handling."""

from telegram import LabeledPrice, Update
from telegram.ext import ContextTypes


PRODUCTS = {
    "basic_monthly": {
        "title": "Vechnost Basic",
        "description": "Monthly access to all themes and questions",
        "prices": [LabeledPrice("Monthly subscription", 25000)],  # 250 Stars
        "subscription_period": 2592000,  # 30 days in seconds
    },
    "premium_monthly": {
        "title": "Vechnost Premium",
        "description": "Premium with AI features",
        "prices": [LabeledPrice("Monthly subscription", 50000)],  # 500 Stars
        "subscription_period": 2592000,
    },
    "lifetime": {
        "title": "Vechnost Lifetime",
        "description": "Lifetime access to all features",
        "prices": [LabeledPrice("One-time purchase", 150000)],  # 1500 Stars
        "subscription_period": None,  # One-time
    },
}


async def send_invoice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    product_id: str,
) -> None:
    """Send payment invoice using Telegram Stars."""
    product = PRODUCTS.get(product_id)
    if not product:
        return

    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=product["title"],
        description=product["description"],
        payload=f"vechnost_{product_id}",
        currency="XTR",  # Telegram Stars
        prices=product["prices"],
        subscription_period=product.get("subscription_period"),
    )


async def handle_successful_payment(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle successful Star payment."""
    payment = update.message.successful_payment
    
    user_id = update.effective_user.id
    payload = payment.invoice_payload
    
    # Grant access based on payload
    if "lifetime" in payload:
        await grant_lifetime_access(user_id)
    elif "premium" in payload:
        await grant_premium_subscription(
            user_id,
            expiration=payment.subscription_expiration_date,
        )
    elif "basic" in payload:
        await grant_basic_subscription(
            user_id,
            expiration=payment.subscription_expiration_date,
        )
    
    # Send confirmation
    await update.message.reply_text(
        get_text("payment.success", session.language)
    )
```

### Анализ рынка и конкурентов

| Продукт | Модель | Цена | Особенности |
|---------|--------|------|-------------|
| Vertellis | Физические карты | $25-45 | Премиум качество, подарочная упаковка |
| Couple Game App | Freemium | $4.99/мес | Много контента, реклама в бесплатной версии |
| Love Nudge | Подписка | $9.99/мес | AI рекомендации, напоминания |
| **Vechnost** | Stars/Subscription | $4.99-29.99 | Telegram интеграция, AI, голос |

### Прогноз доходов

При **1000 активных пользователей**:

| Сценарий | Конверсия | Средний чек | Доход/мес |
|----------|-----------|-------------|-----------|
| Пессимистичный | 3% | $5 | $150 |
| Реалистичный | 7% | $8 | $560 |
| Оптимистичный | 15% | $12 | $1,800 |

**Расходы:**
- Хостинг (Railway/Render): ~$20/мес
- Redis: ~$10/мес
- OpenAI API: ~$30-50/мес (при активном использовании AI)
- Tribute комиссия: 5% от транзакций

**Точка безубыточности:** ~60 платящих пользователей

---

## 📋 Технический план реализации

### Фаза 1: AI Integration (2-3 недели)

```
Неделя 1:
├── [x] Анализ кодовой базы
├── [ ] Добавить OpenAI SDK в зависимости
├── [ ] Реализовать WhisperService
├── [ ] Реализовать обработчик голосовых сообщений
└── [ ] Написать unit тесты

Неделя 2:
├── [ ] Реализовать QuestionGenerator
├── [ ] Реализовать TTSService
├── [ ] Добавить переводы для AI функций
├── [ ] Интеграционные тесты
└── [ ] Документация

Неделя 3:
├── [ ] A/B тестирование
├── [ ] Мониторинг и метрики
├── [ ] Оптимизация производительности
└── [ ] Деплой в продакшн
```

### Фаза 2: 24h Trial & Graphics (2 недели)

```
Неделя 4:
├── [ ] Добавить модель TrialAccess
├── [ ] Миграция Alembic
├── [ ] Реализовать TrialService
├── [ ] Обновить middleware для проверки триала
└── [ ] Scheduled job для напоминаний

Неделя 5:
├── [ ] Улучшить renderer
├── [ ] Добавить градиенты и декорации
├── [ ] Реализовать адаптивный текст
├── [ ] Добавить логотип на карточки
└── [ ] Тестирование на разных устройствах
```

### Фаза 3: Stars Payments (1-2 недели)

```
Неделя 6-7:
├── [ ] Интегрировать Telegram Stars API
├── [ ] Реализовать подписки
├── [ ] Обновить UI для выбора плана
├── [ ] Тестирование платежей
└── [ ] Аналитика конверсий
```

### Фаза 4: Gamification (2-3 недели)

```
Неделя 8-10:
├── [ ] Система достижений
├── [ ] Ежедневный вопрос
├── [ ] Групповые сессии (опционально)
├── [ ] Статистика и прогресс
└── [ ] Финальное тестирование
```

---

## 📎 Приложения

### A. Конфигурация окружения

```env
# .env additions

# OpenAI Configuration
OPENAI_API_KEY=sk-xxx
ENABLE_VOICE_TRANSCRIPTION=true
ENABLE_TTS=true
ENABLE_AI_QUESTIONS=true

# Trial Configuration
TRIAL_DURATION_HOURS=24
TRIAL_REMINDER_HOURS=2

# Telegram Stars
ENABLE_STARS_PAYMENTS=true

# Feature Flags
ENABLE_ACHIEVEMENTS=false
ENABLE_GROUP_SESSIONS=false
ENABLE_DAILY_QUESTION=true
```

### B. Миграции БД

```python
# alembic/versions/xxx_add_trial_access.py
"""Add trial_access table

Revision ID: xxx
"""

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table(
        'trial_access',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('telegram_user_id', sa.BigInteger(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('converted_to_paid', sa.Boolean(), default=False),
        sa.Column('reminder_sent', sa.Boolean(), default=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('telegram_user_id'),
    )
    op.create_index('idx_trial_telegram_user', 'trial_access', ['telegram_user_id'])
    op.create_index('idx_trial_expires', 'trial_access', ['expires_at'])


def downgrade() -> None:
    op.drop_index('idx_trial_expires', 'trial_access')
    op.drop_index('idx_trial_telegram_user', 'trial_access')
    op.drop_table('trial_access')
```

### C. Зависимости

```toml
# pyproject.toml additions

[project]
dependencies = [
    # ... existing dependencies ...
    
    # AI Integration
    "openai>=1.68.0",
    
    # Enhanced Graphics
    "pillow>=10.0.0",
    
    # Background Jobs
    "apscheduler>=3.10.0",
]
```

### D. Метрики успеха

| Метрика | Текущее | Цель (Q2 2026) |
|---------|---------|----------------|
| DAU | ? | 500+ |
| Конверсия trial → paid | N/A | 10%+ |
| Retention D7 | ? | 40%+ |
| Средний чек | $0 | $8+ |
| NPS | ? | 50+ |

---

## 🎯 Выводы

Проект Vechnost имеет **отличную техническую базу** и готов к масштабному развитию. Ключевые рекомендации:

### Немедленные действия (эта неделя)
1. ✅ Добавить OpenAI Whisper для голосового ввода
2. ✅ Реализовать 24-часовой бесплатный пробный период
3. ✅ Улучшить визуальное оформление карточек

### Краткосрочные цели (этот месяц)
4. ⏳ Интегрировать Telegram Stars для платежей
5. ⏳ Добавить генерацию вопросов через GPT
6. ⏳ Реализовать систему достижений

### Долгосрочные цели (квартал)
7. 📅 Групповые игровые сессии
8. 📅 Расширить языковую поддержку
9. 📅 Создать Telegram Mini App

---

**Автор:** AI Assistant (Claude)  
**Дата:** 3 февраля 2026  
**Версия документа:** 1.0

---

> 💡 *"Vechnost — не просто игра. Это инструмент для создания глубоких связей между людьми."*
