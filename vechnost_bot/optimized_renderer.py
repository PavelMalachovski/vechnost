"""Optimized image rendering with caching and performance improvements."""

import asyncio
import hashlib
import io
import os
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFont
import structlog

from vechnost_bot.async_file_ops import AsyncFileManager, AsyncImageManager
from vechnost_bot.monitoring import track_performance

logger = structlog.get_logger("optimized_renderer")


@dataclass
class RenderConfig:
    """Configuration for image rendering."""
    card_width: int = 1080
    card_height: int = 1350
    padding: int = 20
    text_margin: float = 0.9
    line_spacing: float = 1.0
    jpeg_quality: int = 90
    fixed_font_size: int = 53
    cache_enabled: bool = True
    cache_max_size: int = 1000
    cache_ttl: int = 3600  # 1 hour


class ImageCache:
    """LRU cache for rendered images."""

    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        self.max_size = max_size
        self.ttl = ttl
        self._cache: Dict[str, Tuple[bytes, float]] = {}
        self._access_order: list = []

    def _cleanup_expired(self):
        """Remove expired entries."""
        import time
        current_time = time.time()
        expired_keys = [
            key for key, (_, timestamp) in self._cache.items()
            if self.ttl > 0 and current_time - timestamp > self.ttl
        ]

        for key in expired_keys:
            self._remove_key(key)

    def _remove_key(self, key: str):
        """Remove key from cache."""
        if key in self._cache:
            del self._cache[key]
            if key in self._access_order:
                self._access_order.remove(key)

    def _evict_lru(self):
        """Evict least recently used entry."""
        if self._access_order:
            lru_key = self._access_order[0]
            self._remove_key(lru_key)

    def get(self, key: str) -> Optional[bytes]:
        """Get cached image."""
        if key not in self._cache:
            return None

        image_data, timestamp = self._cache[key]
        import time
        current_time = time.time()

        # Check if expired (skip check if ttl is 0)
        if self.ttl > 0 and current_time - timestamp > self.ttl:
            self._remove_key(key)
            return None

        # Update access order
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

        return image_data

    def put(self, key: str, image_data: bytes):
        """Put image in cache."""
        # Cleanup expired entries
        self._cleanup_expired()

        # Evict if cache is full
        while len(self._cache) >= self.max_size:
            self._evict_lru()

        # Add to cache
        import time
        current_time = time.time()
        self._cache[key] = (image_data, current_time)

        # Update access order
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

    def clear(self):
        """Clear cache."""
        self._cache.clear()
        self._access_order.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            'size': len(self._cache),
            'max_size': self.max_size,
            'hit_rate': getattr(self, '_hit_count', 0) / max(getattr(self, '_access_count', 1), 1),
            'ttl': self.ttl
        }


class OptimizedRenderer:
    """Optimized image renderer with caching and performance improvements."""

    def __init__(self, config: Optional[RenderConfig] = None):
        self.config = config or RenderConfig()
        self.cache = ImageCache(
            max_size=self.config.cache_max_size,
            ttl=self.config.cache_ttl
        )
        self._font_cache: Dict[int, ImageFont.FreeTypeFont] = {}
        self._cache_dir = Path("cache/images")
        self._ensure_cache_dir()

    def _ensure_cache_dir(self):
        """Ensure cache directory exists."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(self, text: str, language: str) -> str:
        """Generate cache key for text and language."""
        content = f"{text}:{language}:{self.config.fixed_font_size}"
        return hashlib.md5(content.encode()).hexdigest()

    def _get_cached_font(self, size: int) -> ImageFont.FreeTypeFont:
        """Get cached font or load new one."""
        if size not in self._font_cache:
            try:
                font = ImageFont.truetype("DejaVuSans-Bold.ttf", size)
            except IOError:
                try:
                    font = ImageFont.truetype("arialbd.ttf", size)
                except IOError:
                    font = ImageFont.load_default()
                    logger.warning("using_default_font", size=size)

            self._font_cache[size] = font

        return self._font_cache[size]

    def _wrap_text_optimized(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        """Optimized text wrapping."""
        words = text.split()
        lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = font.getbbox(test_line)
            text_width = bbox[2] - bbox[0]

            if text_width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                    current_line = [word]
                else:
                    # Single word is too long, force break
                    lines.append(word)

        if current_line:
            lines.append(' '.join(current_line))

        return lines

    async def _render_card_async(self, text: str, language: str) -> bytes:
        """Render card asynchronously."""
        # Check cache first
        if self.config.cache_enabled:
            cache_key = self._get_cache_key(text, language)
            cached_image = self.cache.get(cache_key)
            if cached_image:
                logger.debug("cache_hit", cache_key=cache_key)
                return cached_image

        # Render new image
        image_data = await self._render_card_sync(text, language)

        # Cache the result
        if self.config.cache_enabled:
            cache_key = self._get_cache_key(text, language)
            self.cache.put(cache_key, image_data)
            logger.debug("cache_put", cache_key=cache_key)

        return image_data

    async def _render_card_sync(self, text: str, language: str) -> bytes:
        """Synchronous card rendering (run in thread pool)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._render_card_blocking, text, language)

    def _render_card_blocking(self, text: str, language: str) -> bytes:
        """Blocking card rendering."""
        # Create image
        image = Image.new('RGB', (self.config.card_width, self.config.card_height), (255, 255, 255))
        draw = ImageDraw.Draw(image)

        # Get font
        font = self._get_cached_font(self.config.fixed_font_size)

        # Calculate text area
        text_width = int(self.config.card_width * self.config.text_margin)
        text_height = self.config.card_height - (2 * self.config.padding)

        # Wrap text
        lines = self._wrap_text_optimized(text, font, text_width)

        # Calculate line height
        bbox = font.getbbox("Ay")
        line_height = int((bbox[3] - bbox[1]) * self.config.line_spacing)

        # Calculate total text height
        total_text_height = len(lines) * line_height

        # Center text vertically
        start_y = (self.config.card_height - total_text_height) // 2

        # Draw text
        text_color = (53, 0, 39)  # Dark maroon #350027

        for i, line in enumerate(lines):
            bbox = font.getbbox(line)
            line_width = bbox[2] - bbox[0]
            x = (self.config.card_width - line_width) // 2
            y = start_y + (i * line_height)

            draw.text((x, y), line, font=font, fill=text_color)

        # Convert to bytes
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=self.config.jpeg_quality, optimize=True)
        return output.getvalue()

    @track_performance("render_card")
    async def render_card(self, text: str, language: str = "en") -> bytes:
        """
        Render card with text.

        Args:
            text: Text to render
            language: Language for caching

        Returns:
            Rendered image as bytes
        """
        try:
            return await self._render_card_async(text, language)
        except Exception as e:
            logger.error("card_render_error", text=text[:100], error=str(e))
            raise

    async def render_card_to_file(self, text: str, output_path: str, language: str = "en") -> bool:
        """
        Render card and save to file.

        Args:
            text: Text to render
            output_path: Path to save image
            language: Language for caching

        Returns:
            True if successful, False otherwise
        """
        try:
            image_data = await self.render_card(text, language)
            return await AsyncImageManager.save_image(output_path, image_data)
        except Exception as e:
            logger.error("card_render_to_file_error", output_path=output_path, error=str(e))
            return False

    async def preload_common_cards(self, texts: list[str], language: str = "en"):
        """Preload common cards into cache."""
        tasks = [self.render_card(text, language) for text in texts]
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("common_cards_preloaded", count=len(texts))

    def clear_cache(self):
        """Clear render cache."""
        self.cache.clear()
        logger.info("render_cache_cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self.cache.get_stats()

    async def cleanup_old_cache_files(self, max_age_hours: int = 24):
        """Cleanup old cache files."""
        try:
            current_time = asyncio.get_event_loop().time()
            max_age_seconds = max_age_hours * 3600

            files = await AsyncFileManager.list_directory(self._cache_dir)
            deleted_count = 0

            for filename in files:
                file_path = self._cache_dir / filename
                file_time = os.path.getmtime(file_path)

                if current_time - file_time > max_age_seconds:
                    if await AsyncFileManager.delete_file(file_path):
                        deleted_count += 1

            logger.info("cache_cleanup_completed", deleted_files=deleted_count)
            return deleted_count

        except Exception as e:
            logger.error("cache_cleanup_error", error=str(e))
            return 0


class BatchRenderer:
    """Batch renderer for multiple cards."""

    def __init__(self, renderer: OptimizedRenderer, batch_size: int = 10):
        self.renderer = renderer
        self.batch_size = batch_size

    async def render_batch(self, texts: list[str], language: str = "en") -> list[bytes]:
        """
        Render multiple cards in batches.

        Args:
            texts: List of texts to render
            language: Language for caching

        Returns:
            List of rendered images
        """
        results = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            batch_tasks = [self.renderer.render_card(text, language) for text in batch]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error("batch_render_error", error=str(result))
                    results.append(None)
                else:
                    results.append(result)

        logger.info("batch_render_completed", total=len(texts), successful=len([r for r in results if r is not None]))
        return results


# Global instances
renderer = OptimizedRenderer()
batch_renderer = BatchRenderer(renderer)


async def initialize_renderer(config: Optional[RenderConfig] = None):
    """Initialize global renderer."""
    global renderer, batch_renderer
    renderer = OptimizedRenderer(config)
    batch_renderer = BatchRenderer(renderer)
    logger.info("renderer_initialized")


async def cleanup_renderer():
    """Cleanup renderer resources."""
    await renderer.cleanup_old_cache_files()
    logger.info("renderer_cleanup_completed")
