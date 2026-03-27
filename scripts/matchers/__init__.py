"""Public matcher exports used by config/mappings.json dotted paths."""

from .base import (
    always,
    is_code_file,
    is_doc_file,
    is_large_data_file,
    is_unbounded_bash,
)

__all__ = [
    "always",
    "is_code_file",
    "is_doc_file",
    "is_large_data_file",
    "is_unbounded_bash",
]
