"""Async file operations for the Vechnost bot."""

import aiofiles
import asyncio
import os
from pathlib import Path
from typing import Optional, Union, BinaryIO, TextIO
import structlog

logger = structlog.get_logger("async_file_ops")


class AsyncFileManager:
    """Async file operations manager."""

    @staticmethod
    async def read_file(file_path: Union[str, Path], mode: str = 'r') -> Union[str, bytes]:
        """
        Read file asynchronously.

        Args:
            file_path: Path to file
            mode: File mode ('r' for text, 'rb' for binary)

        Returns:
            File contents

        Raises:
            FileNotFoundError: If file doesn't exist
            IOError: If file can't be read
        """
        try:
            async with aiofiles.open(file_path, mode) as f:
                content = await f.read()
                logger.debug("file_read_success", file_path=str(file_path), mode=mode)
                return content
        except FileNotFoundError:
            logger.error("file_not_found", file_path=str(file_path))
            raise
        except Exception as e:
            logger.error("file_read_error", file_path=str(file_path), error=str(e))
            raise IOError(f"Failed to read file {file_path}: {e}")

    @staticmethod
    async def write_file(file_path: Union[str, Path], content: Union[str, bytes], mode: str = 'w') -> None:
        """
        Write file asynchronously.

        Args:
            file_path: Path to file
            content: Content to write
            mode: File mode ('w' for text, 'wb' for binary)

        Raises:
            IOError: If file can't be written
        """
        try:
            # Ensure directory exists
            dir_path = os.path.dirname(file_path)
            if dir_path:  # Only create directory if there's a directory path
                os.makedirs(dir_path, exist_ok=True)

            async with aiofiles.open(file_path, mode) as f:
                await f.write(content)
                logger.debug("file_write_success", file_path=str(file_path), mode=mode)
        except Exception as e:
            logger.error("file_write_error", file_path=str(file_path), error=str(e))
            raise IOError(f"Failed to write file {file_path}: {e}")

    @staticmethod
    async def file_exists(file_path: Union[str, Path]) -> bool:
        """
        Check if file exists asynchronously.

        Args:
            file_path: Path to file

        Returns:
            True if file exists, False otherwise
        """
        try:
            return os.path.exists(file_path)
        except Exception as e:
            logger.error("file_exists_error", file_path=str(file_path), error=str(e))
            return False

    @staticmethod
    async def get_file_size(file_path: Union[str, Path]) -> Optional[int]:
        """
        Get file size asynchronously.

        Args:
            file_path: Path to file

        Returns:
            File size in bytes, or None if file doesn't exist
        """
        try:
            if await AsyncFileManager.file_exists(file_path):
                return os.path.getsize(file_path)
            return None
        except Exception as e:
            logger.error("file_size_error", file_path=str(file_path), error=str(e))
            return None

    @staticmethod
    async def delete_file(file_path: Union[str, Path]) -> bool:
        """
        Delete file asynchronously.

        Args:
            file_path: Path to file

        Returns:
            True if file was deleted, False otherwise
        """
        try:
            if await AsyncFileManager.file_exists(file_path):
                os.remove(file_path)
                logger.debug("file_deleted", file_path=str(file_path))
                return True
            return False
        except Exception as e:
            logger.error("file_delete_error", file_path=str(file_path), error=str(e))
            return False

    @staticmethod
    async def list_directory(dir_path: Union[str, Path]) -> list[str]:
        """
        List directory contents asynchronously.

        Args:
            dir_path: Path to directory

        Returns:
            List of file/directory names
        """
        try:
            if not os.path.isdir(dir_path):
                return []

            files = []
            for item in os.listdir(dir_path):
                files.append(item)

            logger.debug("directory_listed", dir_path=str(dir_path), count=len(files))
            return files
        except Exception as e:
            logger.error("directory_list_error", dir_path=str(dir_path), error=str(e))
            return []

    @staticmethod
    async def create_directory(dir_path: Union[str, Path]) -> bool:
        """
        Create directory asynchronously.

        Args:
            dir_path: Path to directory

        Returns:
            True if directory was created or exists, False otherwise
        """
        try:
            os.makedirs(dir_path, exist_ok=True)
            logger.debug("directory_created", dir_path=str(dir_path))
            return True
        except Exception as e:
            logger.error("directory_create_error", dir_path=str(dir_path), error=str(e))
            return False


class AsyncImageManager:
    """Async image operations manager."""

    @staticmethod
    async def load_image(file_path: Union[str, Path]) -> Optional[bytes]:
        """
        Load image file asynchronously.

        Args:
            file_path: Path to image file

        Returns:
            Image data as bytes, or None if failed
        """
        try:
            image_data = await AsyncFileManager.read_file(file_path, 'rb')
            logger.debug("image_loaded", file_path=str(file_path), size=len(image_data))
            return image_data
        except Exception as e:
            logger.error("image_load_error", file_path=str(file_path), error=str(e))
            return None

    @staticmethod
    async def save_image(file_path: Union[str, Path], image_data: bytes) -> bool:
        """
        Save image file asynchronously.

        Args:
            file_path: Path to save image
            image_data: Image data as bytes

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            await AsyncFileManager.write_file(file_path, image_data, 'wb')
            logger.debug("image_saved", file_path=str(file_path), size=len(image_data))
            return True
        except Exception as e:
            logger.error("image_save_error", file_path=str(file_path), error=str(e))
            return False

    @staticmethod
    async def image_exists(file_path: Union[str, Path]) -> bool:
        """
        Check if image file exists.

        Args:
            file_path: Path to image file

        Returns:
            True if image exists, False otherwise
        """
        return await AsyncFileManager.file_exists(file_path)


class AsyncConfigManager:
    """Async configuration file manager."""

    @staticmethod
    async def load_yaml_config(file_path: Union[str, Path]) -> Optional[dict]:
        """
        Load YAML configuration file asynchronously.

        Args:
            file_path: Path to YAML file

        Returns:
            Configuration dictionary, or None if failed
        """
        try:
            import yaml
            content = await AsyncFileManager.read_file(file_path, 'r')
            config = yaml.safe_load(content)
            logger.debug("yaml_config_loaded", file_path=str(file_path))
            return config
        except Exception as e:
            logger.error("yaml_config_load_error", file_path=str(file_path), error=str(e))
            return None

    @staticmethod
    async def save_yaml_config(file_path: Union[str, Path], config: dict) -> bool:
        """
        Save YAML configuration file asynchronously.

        Args:
            file_path: Path to YAML file
            config: Configuration dictionary

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            import yaml
            content = yaml.dump(config, default_flow_style=False, allow_unicode=True)
            await AsyncFileManager.write_file(file_path, content, 'w')
            logger.debug("yaml_config_saved", file_path=str(file_path))
            return True
        except Exception as e:
            logger.error("yaml_config_save_error", file_path=str(file_path), error=str(e))
            return False


# Convenience functions for common operations
async def read_text_file(file_path: Union[str, Path]) -> str:
    """Read text file asynchronously."""
    return await AsyncFileManager.read_file(file_path, 'r')


async def read_binary_file(file_path: Union[str, Path]) -> bytes:
    """Read binary file asynchronously."""
    return await AsyncFileManager.read_file(file_path, 'rb')


async def write_text_file(file_path: Union[str, Path], content: str) -> None:
    """Write text file asynchronously."""
    await AsyncFileManager.write_file(file_path, content, 'w')


async def write_binary_file(file_path: Union[str, Path], content: bytes) -> None:
    """Write binary file asynchronously."""
    await AsyncFileManager.write_file(file_path, content, 'wb')


async def ensure_directory_exists(dir_path: Union[str, Path]) -> bool:
    """Ensure directory exists, create if necessary."""
    return await AsyncFileManager.create_directory(dir_path)


async def safe_file_operation(operation, *args, **kwargs):
    """
    Safely execute file operation with error handling.

    Args:
        operation: Async function to execute
        *args: Arguments for operation
        **kwargs: Keyword arguments for operation

    Returns:
        Result of operation or None if failed
    """
    try:
        return await operation(*args, **kwargs)
    except Exception as e:
        logger.error("safe_file_operation_error", operation=operation.__name__, error=str(e))
        return None
