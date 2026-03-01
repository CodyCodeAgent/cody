"""Cody - AI coding companion"""

__version__ = "1.3.0"

from .client import (  # noqa: F401
    AsyncCodyClient,
    CodyClient,
    CodyConnectionError,
    CodyError,
    CodyNotFoundError,
    CodyTimeoutError,
)
