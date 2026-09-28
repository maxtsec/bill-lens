"""Lossless storage of the port's Python str (not original provider wire bytes)."""

from sqlalchemy import LargeBinary
from sqlalchemy.types import TypeDecorator


class RawResponseText(TypeDecorator):
    """BYTEA containing UTF-8 with surrogatepass, fixed by migration 0002.

    Keeps NUL, lone/adjacent surrogates, literal escape spellings and normal
    Unicode distinct. No normalization, replacement, JSON parsing or stripping.
    ORM callers continue to read/write str | None. Direct SQL uses encoded bytes.
    """

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("raw_response must be a string or None")
        return value.encode("utf-8", errors="surrogatepass")

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        # Invalid bytes written outside this codec must fail visibly on read.
        return value.decode("utf-8", errors="surrogatepass")
