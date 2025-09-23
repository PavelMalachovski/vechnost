"""Connection pooling for external services."""

import asyncio
import aiohttp
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass
from contextlib import asynccontextmanager
import structlog

logger = structlog.get_logger("connection_pool")


@dataclass
class PoolConfig:
    """Configuration for connection pool."""
    max_connections: int = 10
    max_connections_per_host: int = 5
    keepalive_timeout: int = 30
    connect_timeout: int = 10
    read_timeout: int = 30
    retry_attempts: int = 3
    retry_delay: float = 1.0


class ConnectionPool:
    """Async connection pool for HTTP requests."""

    def __init__(self, config: Optional[PoolConfig] = None):
        self.config = config or PoolConfig()
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()
        self._stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'connection_errors': 0,
            'timeout_errors': 0,
            'last_reset': time.time()
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=self.config.max_connections,
                limit_per_host=self.config.max_connections_per_host,
                keepalive_timeout=self.config.keepalive_timeout,
                enable_cleanup_closed=True
            )

            timeout = aiohttp.ClientTimeout(
                total=self.config.read_timeout,
                connect=self.config.connect_timeout
            )

            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={'User-Agent': 'VechnostBot/1.0'}
            )

            logger.debug("http_session_created", config=self.config.__dict__)

        return self._session

    async def _make_request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> Optional[aiohttp.ClientResponse]:
        """Make HTTP request with retry logic."""
        session = await self._get_session()

        for attempt in range(self.config.retry_attempts):
            try:
                self._stats['total_requests'] += 1

                async with session.request(method, url, **kwargs) as response:
                    if response.status < 500:  # Don't retry client errors
                        self._stats['successful_requests'] += 1
                        return response
                    else:
                        self._stats['failed_requests'] += 1
                        if attempt < self.config.retry_attempts - 1:
                            await asyncio.sleep(self.config.retry_delay * (2 ** attempt))
                            continue
                        return response

            except asyncio.TimeoutError:
                self._stats['timeout_errors'] += 1
                logger.warning("request_timeout", url=url, attempt=attempt + 1)
                if attempt < self.config.retry_attempts - 1:
                    await asyncio.sleep(self.config.retry_delay * (2 ** attempt))
                    continue
                raise

            except aiohttp.ClientError as e:
                self._stats['connection_errors'] += 1
                logger.warning("connection_error", url=url, error=str(e), attempt=attempt + 1)
                if attempt < self.config.retry_attempts - 1:
                    await asyncio.sleep(self.config.retry_delay * (2 ** attempt))
                    continue
                raise

            except Exception as e:
                self._stats['failed_requests'] += 1
                logger.error("request_error", url=url, error=str(e), attempt=attempt + 1)
                raise

        return None

    async def get(self, url: str, **kwargs) -> Optional[aiohttp.ClientResponse]:
        """Make GET request."""
        return await self._make_request_with_retry('GET', url, **kwargs)

    async def post(self, url: str, **kwargs) -> Optional[aiohttp.ClientResponse]:
        """Make POST request."""
        return await self._make_request_with_retry('POST', url, **kwargs)

    async def put(self, url: str, **kwargs) -> Optional[aiohttp.ClientResponse]:
        """Make PUT request."""
        return await self._make_request_with_retry('PUT', url, **kwargs)

    async def delete(self, url: str, **kwargs) -> Optional[aiohttp.ClientResponse]:
        """Make DELETE request."""
        return await self._make_request_with_retry('DELETE', url, **kwargs)

    async def close(self):
        """Close connection pool."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("connection_pool_closed")

    def get_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics."""
        uptime = time.time() - self._stats['last_reset']
        success_rate = (
            self._stats['successful_requests'] / self._stats['total_requests']
            if self._stats['total_requests'] > 0 else 0
        )

        return {
            **self._stats,
            'uptime': uptime,
            'success_rate': success_rate,
            'requests_per_second': self._stats['total_requests'] / uptime if uptime > 0 else 0
        }

    def reset_stats(self):
        """Reset statistics."""
        self._stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'connection_errors': 0,
            'timeout_errors': 0,
            'last_reset': time.time()
        }
        logger.debug("connection_pool_stats_reset")


class TelegramAPIPool:
    """Specialized connection pool for Telegram API."""

    def __init__(self, bot_token: str, config: Optional[PoolConfig] = None):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.pool = ConnectionPool(config)
        self._rate_limit_delay = 0.0

    async def _handle_rate_limit(self, response: aiohttp.ClientResponse):
        """Handle Telegram API rate limiting."""
        if response.status == 429:  # Too Many Requests
            retry_after = int(response.headers.get('Retry-After', 1))
            self._rate_limit_delay = retry_after
            logger.warning("telegram_rate_limit", retry_after=retry_after)
            await asyncio.sleep(retry_after)

    async def make_request(self, method: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Make request to Telegram API."""
        url = f"{self.base_url}/{method}"

        # Add rate limit delay if needed
        if self._rate_limit_delay > 0:
            await asyncio.sleep(self._rate_limit_delay)
            self._rate_limit_delay = 0.0

        response = await self.pool.post(url, **kwargs)

        if response:
            await self._handle_rate_limit(response)

            try:
                data = await response.json()
                if data.get('ok'):
                    return data.get('result')
                else:
                    logger.error("telegram_api_error", error=data.get('description'))
                    return None
            except Exception as e:
                logger.error("telegram_api_response_error", error=str(e))
                return None

        return None

    async def close(self):
        """Close Telegram API pool."""
        await self.pool.close()


class ExternalServicePool:
    """Connection pool for external services."""

    def __init__(self):
        self._pools: Dict[str, ConnectionPool] = {}
        self._configs: Dict[str, PoolConfig] = {}

    def register_service(self, service_name: str, config: Optional[PoolConfig] = None):
        """Register external service."""
        self._configs[service_name] = config or PoolConfig()
        self._pools[service_name] = ConnectionPool(self._configs[service_name])
        logger.debug("external_service_registered", service_name=service_name)

    async def get_pool(self, service_name: str) -> Optional[ConnectionPool]:
        """Get connection pool for service."""
        return self._pools.get(service_name)

    async def make_request(
        self,
        service_name: str,
        method: str,
        url: str,
        **kwargs
    ) -> Optional[aiohttp.ClientResponse]:
        """Make request to external service."""
        pool = await self.get_pool(service_name)
        if not pool:
            logger.error("service_not_registered", service_name=service_name)
            return None

        return await pool._make_request_with_retry(method, url, **kwargs)

    async def close_all(self):
        """Close all connection pools."""
        for service_name, pool in self._pools.items():
            await pool.close()
            logger.debug("external_service_closed", service_name=service_name)

        self._pools.clear()
        self._configs.clear()


# Global instances
telegram_pool: Optional[TelegramAPIPool] = None
external_pool = ExternalServicePool()


async def initialize_telegram_pool(bot_token: str, config: Optional[PoolConfig] = None):
    """Initialize Telegram API connection pool."""
    global telegram_pool
    telegram_pool = TelegramAPIPool(bot_token, config)
    logger.info("telegram_pool_initialized")


async def initialize_external_services():
    """Initialize external service connection pools."""
    # Register common external services
    external_pool.register_service(
        "sentry",
        PoolConfig(
            max_connections=5,
            max_connections_per_host=2,
            connect_timeout=5,
            read_timeout=10
        )
    )

    external_pool.register_service(
        "monitoring",
        PoolConfig(
            max_connections=3,
            max_connections_per_host=1,
            connect_timeout=3,
            read_timeout=5
        )
    )

    logger.info("external_services_initialized")


async def cleanup_connections():
    """Cleanup all connection pools."""
    if telegram_pool:
        await telegram_pool.close()

    await external_pool.close_all()
    logger.info("all_connections_cleaned_up")


@asynccontextmanager
async def managed_telegram_request(method: str, **kwargs):
    """Context manager for Telegram API requests."""
    if not telegram_pool:
        raise RuntimeError("Telegram pool not initialized")

    try:
        result = await telegram_pool.make_request(method, **kwargs)
        yield result
    except Exception as e:
        logger.error("telegram_request_error", method=method, error=str(e))
        raise


@asynccontextmanager
async def managed_external_request(service_name: str, method: str, url: str, **kwargs):
    """Context manager for external service requests."""
    try:
        response = await external_pool.make_request(service_name, method, url, **kwargs)
        yield response
    except Exception as e:
        logger.error("external_request_error", service_name=service_name, method=method, url=url, error=str(e))
        raise
