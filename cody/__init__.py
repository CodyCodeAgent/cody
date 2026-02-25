"""Cody - AI coding companion"""

__version__ = "1.0.0"

from .client import (  # noqa: F401
    AsyncCodyClient,
    CodyClient,
    CodyConnectionError,
    CodyError,
    CodyNotFoundError,
    CodyTimeoutError,
)
