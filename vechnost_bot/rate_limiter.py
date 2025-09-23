"""Rate limiting implementation for the Vechnost bot."""

import time
import asyncio
from typing import Dict, Optional
from collections import defaultdict, deque
from dataclasses import dataclass
from enum import Enum

import structlog

logger = structlog.get_logger("rate_limiter")


class RateLimitType(Enum):
    """Types of rate limiting."""
    COMMAND = "command"
    CALLBACK = "callback"
    MESSAGE = "message"
    IMAGE_RENDER = "image_render"


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    max_requests: int
    time_window: int  # in seconds
    block_duration: int = 300  # 5 minutes default


class RateLimiter:
    """Rate limiter implementation using sliding window algorithm."""

    def __init__(self):
        self._windows: Dict[str, Dict[int, deque]] = defaultdict(lambda: defaultdict(deque))
        self._blocked_users: Dict[int, float] = {}

        # Rate limit configurations
        self._configs = {
            RateLimitType.COMMAND: RateLimitConfig(
                max_requests=10,
                time_window=60,  # 1 minute
                block_duration=300
            ),
            RateLimitType.CALLBACK: RateLimitConfig(
                max_requests=30,
                time_window=60,  # 1 minute
                block_duration=300
            ),
            RateLimitType.MESSAGE: RateLimitConfig(
                max_requests=20,
                time_window=60,  # 1 minute
                block_duration=300
            ),
            RateLimitType.IMAGE_RENDER: RateLimitConfig(
                max_requests=5,
                time_window=60,  # 1 minute
                block_duration=600  # 10 minutes
            )
        }

    def _cleanup_old_requests(self, user_id: int, limit_type: RateLimitType) -> None:
        """Remove old requests outside the time window."""
        config = self._configs[limit_type]
        current_time = time.time()
        window = self._windows[limit_type.value][user_id]

        # Remove requests older than the time window
        while window and window[0] <= current_time - config.time_window:
            window.popleft()

    def _is_user_blocked(self, user_id: int) -> bool:
        """Check if user is currently blocked."""
        if user_id in self._blocked_users:
            if time.time() < self._blocked_users[user_id]:
                return True
            else:
                # Block expired, remove it
                del self._blocked_users[user_id]
        return False

    def _block_user(self, user_id: int, block_duration: int) -> None:
        """Block user for specified duration."""
        self._blocked_users[user_id] = time.time() + block_duration
        logger.warning(
            "user_blocked",
            user_id=user_id,
            block_duration=block_duration,
            block_until=self._blocked_users[user_id]
        )

    def is_allowed(self, user_id: int, limit_type: RateLimitType) -> tuple[bool, Optional[str]]:
        """
        Check if request is allowed for user.

        Returns:
            tuple: (is_allowed, error_message)
        """
        # Check if user is blocked
        if self._is_user_blocked(user_id):
            config = self._configs[limit_type]
            block_remaining = int(self._blocked_users[user_id] - time.time())
            return False, f"Rate limit exceeded. Blocked for {block_remaining} seconds."

        config = self._configs[limit_type]
        current_time = time.time()

        # Clean up old requests
        self._cleanup_old_requests(user_id, limit_type)

        # Check current request count
        window = self._windows[limit_type.value][user_id]

        if len(window) >= config.max_requests:
            # Rate limit exceeded, block user
            self._block_user(user_id, config.block_duration)
            return False, f"Rate limit exceeded. Maximum {config.max_requests} requests per {config.time_window} seconds."

        # Add current request
        window.append(current_time)

        logger.debug(
            "rate_limit_check",
            user_id=user_id,
            limit_type=limit_type.value,
            current_requests=len(window),
            max_requests=config.max_requests,
            time_window=config.time_window
        )

        return True, None

    def get_remaining_requests(self, user_id: int, limit_type: RateLimitType) -> int:
        """Get remaining requests for user in current window."""
        self._cleanup_old_requests(user_id, limit_type)
        config = self._configs[limit_type]
        current_requests = len(self._windows[limit_type.value][user_id])
        return max(0, config.max_requests - current_requests)

    def get_reset_time(self, user_id: int, limit_type: RateLimitType) -> Optional[float]:
        """Get time when rate limit resets for user."""
        window = self._windows[limit_type.value][user_id]
        if not window:
            return None

        config = self._configs[limit_type]
        return window[0] + config.time_window

    def reset_user_limits(self, user_id: int) -> None:
        """Reset all rate limits for a user."""
        for limit_type in RateLimitType:
            self._windows[limit_type.value][user_id].clear()

        if user_id in self._blocked_users:
            del self._blocked_users[user_id]

        logger.info("user_limits_reset", user_id=user_id)


# Global rate limiter instance
rate_limiter = RateLimiter()


def rate_limit(limit_type: RateLimitType):
    """Decorator for rate limiting functions."""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            # Extract user_id from arguments
            user_id = None

            # Try to get user_id from different argument patterns
            for arg in args:
                if hasattr(arg, 'effective_user') and arg.effective_user:
                    user_id = arg.effective_user.id
                    break
                elif hasattr(arg, 'from_user') and arg.from_user:
                    user_id = arg.from_user.id
                    break
                elif hasattr(arg, 'message') and arg.message and arg.message.from_user:
                    user_id = arg.message.from_user.id
                    break

            if user_id is None:
                logger.warning("rate_limit_no_user_id", function=func.__name__)
                return await func(*args, **kwargs)

            # Check rate limit
            is_allowed, error_message = rate_limiter.is_allowed(user_id, limit_type)

            if not is_allowed:
                logger.warning(
                    "rate_limit_exceeded",
                    user_id=user_id,
                    limit_type=limit_type.value,
                    function=func.__name__,
                    error_message=error_message
                )

                # Try to send error message to user
                try:
                    if hasattr(args[0], 'message') and args[0].message:
                        await args[0].message.reply_text(
                            f"⚠️ {error_message}\n\nPlease wait before trying again."
                        )
                    elif hasattr(args[0], 'edit_message_text'):
                        await args[0].edit_message_text(
                            f"⚠️ {error_message}\n\nPlease wait before trying again."
                        )
                except Exception as e:
                    logger.error("rate_limit_error_message_failed", error=str(e))

                return

            return await func(*args, **kwargs)

        def sync_wrapper(*args, **kwargs):
            # Extract user_id from arguments
            user_id = None

            for arg in args:
                if hasattr(arg, 'effective_user') and arg.effective_user:
                    user_id = arg.effective_user.id
                    break
                elif hasattr(arg, 'from_user') and arg.from_user:
                    user_id = arg.from_user.id
                    break
                elif hasattr(arg, 'message') and arg.message and arg.message.from_user:
                    user_id = arg.message.from_user.id
                    break

            if user_id is None:
                logger.warning("rate_limit_no_user_id", function=func.__name__)
                return func(*args, **kwargs)

            # Check rate limit
            is_allowed, error_message = rate_limiter.is_allowed(user_id, limit_type)

            if not is_allowed:
                logger.warning(
                    "rate_limit_exceeded",
                    user_id=user_id,
                    limit_type=limit_type.value,
                    function=func.__name__,
                    error_message=error_message
                )
                return

            return func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def get_rate_limit_info(user_id: int, limit_type: RateLimitType) -> dict:
    """Get rate limit information for user."""
    remaining = rate_limiter.get_remaining_requests(user_id, limit_type)
    reset_time = rate_limiter.get_reset_time(user_id, limit_type)
    is_blocked = rate_limiter._is_user_blocked(user_id)

    return {
        "remaining_requests": remaining,
        "reset_time": reset_time,
        "is_blocked": is_blocked,
        "block_until": rate_limiter._blocked_users.get(user_id)
    }
