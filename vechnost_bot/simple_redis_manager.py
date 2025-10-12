"""Simplified Redis manager without background tasks."""

import subprocess
import time
import os
from typing import Optional
import structlog
from pathlib import Path

logger = structlog.get_logger(__name__)


class SimpleRedisManager:
    """Simplified Redis manager without async background tasks."""

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

    def start_redis(self) -> bool:
        """Start Redis instance with retry logic (synchronous)."""
        logger.info("starting_redis_instance")

        # Create Redis data directory
        self.redis_data_dir.mkdir(exist_ok=True)

        for attempt in range(self.max_startup_attempts):
            try:
                logger.info("redis_startup_attempt", attempt=attempt + 1, max_attempts=self.max_startup_attempts)

                if self._start_redis_process():
                    if self._wait_for_redis_ready():
                        logger.info("redis_started_successfully", port=self.redis_port)
                        return True
                    else:
                        logger.warning("redis_startup_timeout", attempt=attempt + 1)
                        self._stop_redis_process()
                else:
                    logger.warning("redis_process_start_failed", attempt=attempt + 1)

            except Exception as e:
                logger.error("redis_startup_error", attempt=attempt + 1, error=str(e))

            if attempt < self.max_startup_attempts - 1:
                wait_time = (attempt + 1) * 2  # Exponential backoff
                logger.info("redis_retry_wait", wait_time=wait_time)
                time.sleep(wait_time)

        logger.error("redis_startup_failed_all_attempts")
        return False

    def _start_redis_process(self) -> bool:
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

    def _wait_for_redis_ready(self) -> bool:
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

            time.sleep(1)

        logger.warning("redis_ready_timeout")
        return False

    def _stop_redis_process(self):
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

    def health_check(self) -> bool:
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

    def cleanup(self):
        """Cleanup Redis resources."""
        logger.info("redis_manager_cleanup")
        self._stop_redis_process()

        # Clean up temporary files
        try:
            if self.redis_log_file.exists():
                self.redis_log_file.unlink()
            if self.redis_data_dir.exists():
                import shutil
                shutil.rmtree(self.redis_data_dir)
        except Exception as e:
            logger.error("redis_cleanup_error", error=str(e))


class SimpleRedisAutoStartManager:
    """Simplified Redis auto-start manager without background tasks."""

    def __init__(self):
        self.redis_manager = SimpleRedisManager()
        self.redis_started = False
        self.fallback_to_memory = False
        self.external_redis_url: Optional[str] = None

    def initialize(self) -> bool:
        """Initialize Redis with auto-start and fallback (synchronous)."""
        logger.info("initializing_redis_auto_start")

        # First, check if REDIS_URL is provided in environment
        redis_url_env = os.getenv("REDIS_URL")
        logger.info("redis_url_from_env", redis_url=redis_url_env or "NOT_SET")
        
        if redis_url_env and redis_url_env != "redis://localhost:6379":
            logger.info("using_external_redis_url", url=redis_url_env)
            self.external_redis_url = redis_url_env
            self.redis_started = True
            self.fallback_to_memory = False
            logger.info("external_redis_configured")
            return True

        # Try to start Redis locally only if no external URL is provided
        if self.redis_manager.start_redis():
            self.redis_started = True
            self.fallback_to_memory = False
            logger.info("redis_auto_start_success")
            return True
        else:
            # Fallback to in-memory storage
            self.redis_started = False
            self.fallback_to_memory = True
            logger.warning("redis_auto_start_failed_fallback_to_memory")
            return False

    def get_storage_mode(self) -> str:
        """Get current storage mode."""
        if self.redis_started and not self.fallback_to_memory:
            return "redis"
        else:
            return "memory"

    def get_redis_url(self) -> str:
        """Get Redis URL for connection."""
        if self.external_redis_url:
            return self.external_redis_url
        elif self.redis_started and not self.fallback_to_memory:
            return f"redis://{self.redis_manager.redis_host}:{self.redis_manager.redis_port}"
        else:
            return "redis://localhost:6379"  # Will fail and trigger fallback

    def cleanup(self):
        """Cleanup Redis manager."""
        self.redis_manager.cleanup()


# Global simplified Redis auto-start manager
simple_redis_auto_start_manager = SimpleRedisAutoStartManager()


def initialize_simple_redis_auto_start() -> bool:
    """Initialize Redis with auto-start (synchronous)."""
    return simple_redis_auto_start_manager.initialize()


def get_simple_redis_storage_mode() -> str:
    """Get current Redis storage mode."""
    return simple_redis_auto_start_manager.get_storage_mode()


def get_simple_redis_connection_url() -> str:
    """Get Redis connection URL."""
    return simple_redis_auto_start_manager.get_redis_url()


def cleanup_simple_redis_auto_start():
    """Cleanup Redis auto-start manager."""
    simple_redis_auto_start_manager.cleanup()
