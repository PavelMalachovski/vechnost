"""Redis management system with auto-start and fallback capabilities."""

import asyncio
import subprocess
import time
import signal
import os
import sys
from typing import Optional, Dict, Any
import structlog
from pathlib import Path

from .config import settings

logger = structlog.get_logger(__name__)


class RedisManager:
    """Manages Redis instance lifecycle with auto-start and health monitoring."""

    def __init__(self):
        self.redis_process: Optional[subprocess.Popen] = None
        self.redis_port = 6379
        self.redis_host = "localhost"

        # Use appropriate temp directory for the platform
        import tempfile
        temp_dir = Path(tempfile.gettempdir())
        self.redis_data_dir = temp_dir / "redis_data"
        self.redis_log_file = temp_dir / "redis.log"

        self.max_startup_attempts = 3
        self.startup_timeout = 30
        self.health_check_interval = 5
        self._shutdown_requested = False

    async def start_redis(self) -> bool:
        """Start Redis instance with retry logic."""
        logger.info("starting_redis_instance")

        # Create Redis data directory
        self.redis_data_dir.mkdir(exist_ok=True)

        for attempt in range(self.max_startup_attempts):
            try:
                logger.info("redis_startup_attempt", attempt=attempt + 1, max_attempts=self.max_startup_attempts)

                if await self._start_redis_process():
                    if await self._wait_for_redis_ready():
                        logger.info("redis_started_successfully", port=self.redis_port)
                        return True
                    else:
                        logger.warning("redis_startup_timeout", attempt=attempt + 1)
                        await self._stop_redis_process()
                else:
                    logger.warning("redis_process_start_failed", attempt=attempt + 1)

            except Exception as e:
                logger.error("redis_startup_error", attempt=attempt + 1, error=str(e))

            if attempt < self.max_startup_attempts - 1:
                wait_time = (attempt + 1) * 2  # Exponential backoff
                logger.info("redis_retry_wait", wait_time=wait_time)
                await asyncio.sleep(wait_time)

        logger.error("redis_startup_failed_all_attempts")
        return False

    async def _start_redis_process(self) -> bool:
        """Start Redis process."""
        try:
            # Redis command with optimized configuration
            redis_cmd = [
                "redis-server",
                "--port", str(self.redis_port),
                "--bind", "127.0.0.1",
                "--dir", str(self.redis_data_dir),
                "--logfile", str(self.redis_log_file),
                "--loglevel", "notice",
                "--maxmemory", "256mb",
                "--maxmemory-policy", "allkeys-lru",
                "--save", "900", "1",  # Save every 15 minutes if at least 1 key changed
                "--save", "300", "10",  # Save every 5 minutes if at least 10 keys changed
                "--save", "60", "10000",  # Save every minute if at least 10000 keys changed
                "--appendonly", "yes",  # Enable AOF for durability
                "--appendfsync", "everysec",  # Sync AOF every second
                "--tcp-keepalive", "60",  # TCP keepalive
                "--timeout", "300",  # Client timeout
                "--databases", "16",  # Number of databases
                "--daemonize", "no",  # Don't daemonize (run in foreground)
            ]

            logger.debug("redis_command", cmd=" ".join(redis_cmd))

            # Start Redis process
            self.redis_process = subprocess.Popen(
                redis_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid if os.name != 'nt' else None
            )

            logger.info("redis_process_started", pid=self.redis_process.pid)
            return True

        except FileNotFoundError:
            logger.error("redis_server_not_found",
                        message="Redis server binary not found. Please install Redis or use Docker.")
            return False
        except Exception as e:
            logger.error("redis_process_start_error", error=str(e))
            return False

    async def _wait_for_redis_ready(self) -> bool:
        """Wait for Redis to be ready to accept connections."""
        logger.info("waiting_for_redis_ready", timeout=self.startup_timeout)

        start_time = time.time()
        while time.time() - start_time < self.startup_timeout:
            try:
                # Try to connect to Redis
                result = subprocess.run(
                    ["redis-cli", "-p", str(self.redis_port), "ping"],
                    capture_output=True,
                    text=True,
                    timeout=2
                )

                if result.returncode == 0 and "PONG" in result.stdout:
                    logger.info("redis_ready_confirmed")
                    return True

            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

            await asyncio.sleep(1)

        logger.warning("redis_ready_timeout")
        return False

    async def _stop_redis_process(self):
        """Stop Redis process gracefully."""
        if self.redis_process and self.redis_process.poll() is None:
            try:
                logger.info("stopping_redis_process", pid=self.redis_process.pid)

                # Try graceful shutdown first
                self.redis_process.terminate()

                # Wait for graceful shutdown
                try:
                    self.redis_process.wait(timeout=10)
                    logger.info("redis_process_stopped_gracefully")
                except subprocess.TimeoutExpired:
                    # Force kill if graceful shutdown fails
                    logger.warning("redis_process_force_kill")
                    self.redis_process.kill()
                    self.redis_process.wait()

            except Exception as e:
                logger.error("redis_process_stop_error", error=str(e))
            finally:
                self.redis_process = None

    async def health_check(self) -> bool:
        """Check if Redis is healthy."""
        if not self.redis_process or self.redis_process.poll() is not None:
            return False

        try:
            result = subprocess.run(
                ["redis-cli", "-p", str(self.redis_port), "ping"],
                capture_output=True,
                text=True,
                timeout=2
            )
            return result.returncode == 0 and "PONG" in result.stdout
        except Exception:
            return False

    async def get_redis_info(self) -> Dict[str, Any]:
        """Get Redis server information."""
        try:
            result = subprocess.run(
                ["redis-cli", "-p", str(self.redis_port), "info"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                info = {}
                for line in result.stdout.split('\n'):
                    if ':' in line and not line.startswith('#'):
                        key, value = line.split(':', 1)
                        info[key.strip()] = value.strip()
                return info
        except Exception as e:
            logger.error("redis_info_error", error=str(e))

        return {}

    async def cleanup(self):
        """Cleanup Redis resources."""
        logger.info("redis_manager_cleanup")
        await self._stop_redis_process()

        # Clean up temporary files
        try:
            if self.redis_log_file.exists():
                self.redis_log_file.unlink()
            if self.redis_data_dir.exists():
                import shutil
                shutil.rmtree(self.redis_data_dir)
        except Exception as e:
            logger.error("redis_cleanup_error", error=str(e))

    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info("shutdown_signal_received", signal=signum)
            self._shutdown_requested = True

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def is_shutdown_requested(self) -> bool:
        """Check if shutdown was requested."""
        return self._shutdown_requested


class RedisAutoStartManager:
    """High-level Redis auto-start manager with fallback strategy."""

    def __init__(self):
        self.redis_manager = RedisManager()
        self.redis_started = False
        self.fallback_to_memory = False

    async def initialize(self) -> bool:
        """Initialize Redis with auto-start and fallback."""
        logger.info("initializing_redis_auto_start")

        # Setup signal handlers
        self.redis_manager.setup_signal_handlers()

        # Try to start Redis
        if await self.redis_manager.start_redis():
            self.redis_started = True
            self.fallback_to_memory = False
            logger.info("redis_auto_start_success")

            # Start background health monitoring
            asyncio.create_task(self._health_monitor())

            return True
        else:
            # Fallback to in-memory storage
            self.redis_started = False
            self.fallback_to_memory = True
            logger.warning("redis_auto_start_failed_fallback_to_memory")
            return False

    async def _health_monitor(self):
        """Background health monitoring for Redis."""
        logger.info("redis_health_monitor_started")

        while not await self.redis_manager.is_shutdown_requested():
            try:
                if not await self.redis_manager.health_check():
                    logger.warning("redis_health_check_failed")

                    # Try to restart Redis
                    if await self.redis_manager.start_redis():
                        logger.info("redis_restart_successful")
                    else:
                        logger.error("redis_restart_failed_fallback_to_memory")
                        self.fallback_to_memory = True
                        break

                await asyncio.sleep(self.redis_manager.health_check_interval)

            except Exception as e:
                logger.error("redis_health_monitor_error", error=str(e))
                await asyncio.sleep(self.redis_manager.health_check_interval)

        logger.info("redis_health_monitor_stopped")

    async def get_storage_mode(self) -> str:
        """Get current storage mode."""
        if self.redis_started and not self.fallback_to_memory:
            return "redis"
        else:
            return "memory"

    async def get_redis_url(self) -> str:
        """Get Redis URL for connection."""
        if self.redis_started and not self.fallback_to_memory:
            return f"redis://{self.redis_manager.redis_host}:{self.redis_manager.redis_port}"
        else:
            return "redis://localhost:6379"  # Will fail and trigger fallback

    async def cleanup(self):
        """Cleanup Redis manager."""
        await self.redis_manager.cleanup()


# Global Redis auto-start manager
redis_auto_start_manager = RedisAutoStartManager()


async def initialize_redis_auto_start() -> bool:
    """Initialize Redis with auto-start."""
    return await redis_auto_start_manager.initialize()


async def get_redis_storage_mode() -> str:
    """Get current Redis storage mode."""
    return await redis_auto_start_manager.get_storage_mode()


async def get_redis_connection_url() -> str:
    """Get Redis connection URL."""
    return await redis_auto_start_manager.get_redis_url()


async def cleanup_redis_auto_start():
    """Cleanup Redis auto-start manager."""
    await redis_auto_start_manager.cleanup()
