"""Tests for performance optimization modules."""

import pytest
import asyncio
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from vechnost_bot.async_file_ops import (
    AsyncFileManager,
    AsyncImageManager,
    AsyncConfigManager,
    read_text_file,
    read_binary_file,
    write_text_file,
    write_binary_file,
    ensure_directory_exists,
    safe_file_operation
)
from vechnost_bot.connection_pool import (
    ConnectionPool,
    PoolConfig,
    TelegramAPIPool,
    ExternalServicePool,
    initialize_telegram_pool,
    initialize_external_services,
    cleanup_connections
)
from vechnost_bot.optimized_renderer import (
    OptimizedRenderer,
    RenderConfig,
    ImageCache,
    BatchRenderer,
    initialize_renderer,
    cleanup_renderer
)


class TestAsyncFileManager:
    """Test async file operations."""

    @pytest.fixture
    def temp_file(self):
        """Create temporary file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            return f.name

    @pytest.fixture
    def temp_binary_file(self):
        """Create temporary binary file for testing."""
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
            f.write(b"test binary content")
            return f.name

    def teardown_method(self):
        """Clean up temporary files."""
        # Clean up any temporary files created during tests
        pass

    @pytest.mark.asyncio
    async def test_read_file_text(self, temp_file):
        """Test reading text file."""
        content = await AsyncFileManager.read_file(temp_file, 'r')
        assert content == "test content"

        # Clean up
        os.unlink(temp_file)

    @pytest.mark.asyncio
    async def test_read_file_binary(self, temp_binary_file):
        """Test reading binary file."""
        content = await AsyncFileManager.read_file(temp_binary_file, 'rb')
        assert content == b"test binary content"

        # Clean up
        os.unlink(temp_binary_file)

    @pytest.mark.asyncio
    async def test_read_file_not_found(self):
        """Test reading non-existent file."""
        with pytest.raises(FileNotFoundError):
            await AsyncFileManager.read_file("nonexistent.txt", 'r')

    @pytest.mark.asyncio
    async def test_write_file_text(self):
        """Test writing text file."""
        temp_path = "test_write.txt"
        try:
            await AsyncFileManager.write_file(temp_path, "test content", 'w')

            # Verify content
            content = await AsyncFileManager.read_file(temp_path, 'r')
            assert content == "test content"
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_write_file_binary(self):
        """Test writing binary file."""
        temp_path = "test_write.bin"
        try:
            await AsyncFileManager.write_file(temp_path, b"test binary content", 'wb')

            # Verify content
            content = await AsyncFileManager.read_file(temp_path, 'rb')
            assert content == b"test binary content"
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_file_exists(self):
        """Test file existence check."""
        temp_path = "test_exists.txt"
        try:
            # File doesn't exist
            assert await AsyncFileManager.file_exists(temp_path) is False

            # Create file
            await AsyncFileManager.write_file(temp_path, "test", 'w')

            # File exists
            assert await AsyncFileManager.file_exists(temp_path) is True
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_get_file_size(self):
        """Test getting file size."""
        temp_path = "test_size.txt"
        try:
            # File doesn't exist
            size = await AsyncFileManager.get_file_size(temp_path)
            assert size is None

            # Create file
            content = "test content"
            await AsyncFileManager.write_file(temp_path, content, 'w')

            # Get size
            size = await AsyncFileManager.get_file_size(temp_path)
            assert size == len(content.encode())
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_delete_file(self):
        """Test file deletion."""
        temp_path = "test_delete.txt"

        # Create file
        await AsyncFileManager.write_file(temp_path, "test", 'w')
        assert await AsyncFileManager.file_exists(temp_path) is True

        # Delete file
        result = await AsyncFileManager.delete_file(temp_path)
        assert result is True
        assert await AsyncFileManager.file_exists(temp_path) is False

    @pytest.mark.asyncio
    async def test_list_directory(self):
        """Test directory listing."""
        temp_dir = "test_dir"
        try:
            # Create directory
            await AsyncFileManager.create_directory(temp_dir)

            # Create files
            await AsyncFileManager.write_file(f"{temp_dir}/file1.txt", "content1", 'w')
            await AsyncFileManager.write_file(f"{temp_dir}/file2.txt", "content2", 'w')

            # List directory
            files = await AsyncFileManager.list_directory(temp_dir)
            assert len(files) == 2
            assert "file1.txt" in files
            assert "file2.txt" in files
        finally:
            # Clean up
            for file in ["file1.txt", "file2.txt"]:
                if os.path.exists(f"{temp_dir}/{file}"):
                    os.unlink(f"{temp_dir}/{file}")
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)

    @pytest.mark.asyncio
    async def test_create_directory(self):
        """Test directory creation."""
        temp_dir = "test_create_dir"
        try:
            result = await AsyncFileManager.create_directory(temp_dir)
            assert result is True
            assert os.path.exists(temp_dir)
            assert os.path.isdir(temp_dir)
        finally:
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)


class TestAsyncImageManager:
    """Test async image operations."""

    @pytest.mark.asyncio
    async def test_load_image(self):
        """Test loading image."""
        # Create a simple test image
        from PIL import Image
        temp_path = "test_image.png"
        try:
            # Create simple image
            img = Image.new('RGB', (10, 10), color='red')
            img.save(temp_path)

            # Load image
            image_data = await AsyncImageManager.load_image(temp_path)
            assert image_data is not None
            assert isinstance(image_data, bytes)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_save_image(self):
        """Test saving image."""
        temp_path = "test_save_image.png"
        try:
            # Create test image data
            from PIL import Image
            import io
            img = Image.new('RGB', (10, 10), color='blue')
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            image_data = img_bytes.getvalue()

            # Save image
            result = await AsyncImageManager.save_image(temp_path, image_data)
            assert result is True

            # Verify image exists
            assert await AsyncImageManager.image_exists(temp_path) is True
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_image_exists(self):
        """Test image existence check."""
        temp_path = "test_image_exists.png"

        # Image doesn't exist
        assert await AsyncImageManager.image_exists(temp_path) is False

        # Create image
        from PIL import Image
        img = Image.new('RGB', (10, 10), color='green')
        img.save(temp_path)

        try:
            # Image exists
            assert await AsyncImageManager.image_exists(temp_path) is True
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestAsyncConfigManager:
    """Test async config operations."""

    @pytest.mark.asyncio
    async def test_load_yaml_config(self):
        """Test loading YAML config."""
        temp_path = "test_config.yaml"
        try:
            # Create YAML file
            yaml_content = """
            test:
              key1: value1
              key2: value2
            """
            await AsyncFileManager.write_file(temp_path, yaml_content, 'w')

            # Load config
            config = await AsyncConfigManager.load_yaml_config(temp_path)
            assert config is not None
            assert config['test']['key1'] == 'value1'
            assert config['test']['key2'] == 'value2'
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_save_yaml_config(self):
        """Test saving YAML config."""
        temp_path = "test_save_config.yaml"
        try:
            # Create config
            config = {
                'test': {
                    'key1': 'value1',
                    'key2': 'value2'
                }
            }

            # Save config
            result = await AsyncConfigManager.save_yaml_config(temp_path, config)
            assert result is True

            # Verify file exists
            assert await AsyncFileManager.file_exists(temp_path) is True
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestConnectionPool:
    """Test connection pooling."""

    def test_pool_initialization(self):
        """Test pool initialization."""
        config = PoolConfig(max_connections=5)
        pool = ConnectionPool(config)
        assert pool.config.max_connections == 5

    @pytest.mark.asyncio
    async def test_pool_stats(self):
        """Test pool statistics."""
        pool = ConnectionPool()
        stats = pool.get_stats()

        assert 'total_requests' in stats
        assert 'successful_requests' in stats
        assert 'failed_requests' in stats
        assert 'uptime' in stats
        assert 'success_rate' in stats

    @pytest.mark.asyncio
    async def test_pool_close(self):
        """Test pool closing."""
        pool = ConnectionPool()
        await pool.close()  # Should not raise exception

    def test_reset_stats(self):
        """Test statistics reset."""
        pool = ConnectionPool()
        pool.reset_stats()
        stats = pool.get_stats()
        assert stats['total_requests'] == 0


class TestTelegramAPIPool:
    """Test Telegram API pool."""

    def test_telegram_pool_initialization(self):
        """Test Telegram API pool initialization."""
        pool = TelegramAPIPool("test_token")
        assert pool.bot_token == "test_token"
        assert "test_token" in pool.base_url

    @pytest.mark.asyncio
    async def test_telegram_pool_close(self):
        """Test Telegram API pool closing."""
        pool = TelegramAPIPool("test_token")
        await pool.close()  # Should not raise exception


class TestExternalServicePool:
    """Test external service pool."""

    def test_register_service(self):
        """Test service registration."""
        pool = ExternalServicePool()
        config = PoolConfig(max_connections=3)

        pool.register_service("test_service", config)
        assert "test_service" in pool._pools

    @pytest.mark.asyncio
    async def test_get_pool(self):
        """Test getting service pool."""
        pool = ExternalServicePool()
        pool.register_service("test_service")

        service_pool = await pool.get_pool("test_service")
        assert service_pool is not None

        # Test non-existent service
        service_pool = await pool.get_pool("nonexistent")
        assert service_pool is None

    @pytest.mark.asyncio
    async def test_close_all(self):
        """Test closing all pools."""
        pool = ExternalServicePool()
        pool.register_service("test_service1")
        pool.register_service("test_service2")

        await pool.close_all()
        assert len(pool._pools) == 0


class TestImageCache:
    """Test image cache."""

    def test_cache_initialization(self):
        """Test cache initialization."""
        cache = ImageCache(max_size=100, ttl=3600)
        assert cache.max_size == 100
        assert cache.ttl == 3600

    def test_cache_put_get(self):
        """Test cache put and get."""
        cache = ImageCache()
        key = "test_key"
        data = b"test_data"

        # Put data
        cache.put(key, data)

        # Get data
        retrieved = cache.get(key)
        assert retrieved == data

    def test_cache_expiration(self):
        """Test cache expiration."""
        cache = ImageCache(ttl=1)  # 1 second TTL
        key = "test_key"
        data = b"test_data"

        # Put data
        cache.put(key, data)

        # Force expiration by manually setting timestamp to past
        import time
        cache._cache[key] = (data, time.time() - 2)  # Set timestamp to 2 seconds ago

        # Get data (should be expired)
        retrieved = cache.get(key)
        assert retrieved is None

    def test_cache_lru_eviction(self):
        """Test LRU eviction."""
        cache = ImageCache(max_size=2)

        # Add items up to limit
        cache.put("key1", b"data1")
        cache.put("key2", b"data2")

        # Add one more (should evict key1)
        cache.put("key3", b"data3")

        assert cache.get("key1") is None
        assert cache.get("key2") == b"data2"
        assert cache.get("key3") == b"data3"

    def test_cache_clear(self):
        """Test cache clearing."""
        cache = ImageCache()
        cache.put("key1", b"data1")
        cache.put("key2", b"data2")

        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_cache_stats(self):
        """Test cache statistics."""
        cache = ImageCache()
        cache.put("key1", b"data1")

        stats = cache.get_stats()
        assert 'size' in stats
        assert 'max_size' in stats
        assert 'hit_rate' in stats
        assert 'ttl' in stats


class TestOptimizedRenderer:
    """Test optimized renderer."""

    def test_renderer_initialization(self):
        """Test renderer initialization."""
        config = RenderConfig(card_width=800, card_height=1000)
        renderer = OptimizedRenderer(config)
        assert renderer.config.card_width == 800
        assert renderer.config.card_height == 1000

    @pytest.mark.asyncio
    async def test_render_card(self):
        """Test card rendering."""
        renderer = OptimizedRenderer()

        # Mock PIL operations to avoid actual image rendering
        with patch('vechnost_bot.optimized_renderer.Image.new') as mock_new, \
             patch('vechnost_bot.optimized_renderer.ImageDraw.Draw'), \
             patch('vechnost_bot.optimized_renderer.ImageFont.truetype') as mock_font:

            # Mock the Image instance's save method
            mock_image = MagicMock()
            mock_image.save = MagicMock()
            mock_new.return_value = mock_image

            # Mock font with proper methods
            mock_font_instance = MagicMock()
            mock_font_instance.getbbox.return_value = (0, 0, 100, 20)  # width=100, height=20
            mock_font_instance.getlength.return_value = 50  # text width
            mock_font.return_value = mock_font_instance

            result = await renderer.render_card("Test text")
            assert isinstance(result, bytes)

    def test_get_cache_key(self):
        """Test cache key generation."""
        renderer = OptimizedRenderer()
        key1 = renderer._get_cache_key("text1", "en")
        key2 = renderer._get_cache_key("text2", "en")
        key3 = renderer._get_cache_key("text1", "ru")

        assert key1 != key2
        assert key1 != key3
        assert key2 != key3

    def test_get_cached_font(self):
        """Test font caching."""
        renderer = OptimizedRenderer()

        with patch('vechnost_bot.optimized_renderer.ImageFont.truetype') as mock_font:
            mock_font.return_value = MagicMock()

            # First call
            font1 = renderer._get_cached_font(50)

            # Second call (should use cache)
            font2 = renderer._get_cached_font(50)

            assert font1 is font2
            mock_font.assert_called_once()

    def test_clear_cache(self):
        """Test cache clearing."""
        renderer = OptimizedRenderer()
        renderer.cache.put("test_key", b"test_data")

        renderer.clear_cache()
        assert renderer.cache.get("test_key") is None

    def test_get_cache_stats(self):
        """Test cache statistics."""
        renderer = OptimizedRenderer()
        stats = renderer.get_cache_stats()

        assert 'size' in stats
        assert 'max_size' in stats
        assert 'hit_rate' in stats
        assert 'ttl' in stats


class TestBatchRenderer:
    """Test batch renderer."""

    def test_batch_renderer_initialization(self):
        """Test batch renderer initialization."""
        renderer = OptimizedRenderer()
        batch_renderer = BatchRenderer(renderer, batch_size=5)
        assert batch_renderer.batch_size == 5

    @pytest.mark.asyncio
    async def test_render_batch(self):
        """Test batch rendering."""
        renderer = OptimizedRenderer()
        batch_renderer = BatchRenderer(renderer, batch_size=2)

        # Mock render_card method
        with patch.object(renderer, 'render_card', return_value=b"rendered_image"):
            texts = ["text1", "text2", "text3"]
            results = await batch_renderer.render_batch(texts)

            assert len(results) == 3
            assert all(result == b"rendered_image" for result in results)


class TestConvenienceFunctions:
    """Test convenience functions."""

    @pytest.mark.asyncio
    async def test_read_text_file(self):
        """Test read_text_file convenience function."""
        temp_path = "test_convenience.txt"
        try:
            await AsyncFileManager.write_file(temp_path, "test content", 'w')
            content = await read_text_file(temp_path)
            assert content == "test content"
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_write_text_file(self):
        """Test write_text_file convenience function."""
        temp_path = "test_convenience_write.txt"
        try:
            await write_text_file(temp_path, "test content")
            content = await AsyncFileManager.read_file(temp_path, 'r')
            assert content == "test content"
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_ensure_directory_exists(self):
        """Test ensure_directory_exists convenience function."""
        temp_dir = "test_convenience_dir"
        try:
            result = await ensure_directory_exists(temp_dir)
            assert result is True
            assert os.path.exists(temp_dir)
        finally:
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)

    @pytest.mark.asyncio
    async def test_safe_file_operation(self):
        """Test safe_file_operation convenience function."""
        async def test_operation():
            return "success"

        result = await safe_file_operation(test_operation)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_safe_file_operation_error(self):
        """Test safe_file_operation with error."""
        async def failing_operation():
            raise Exception("test error")

        result = await safe_file_operation(failing_operation)
        assert result is None
