"""
Matcher functions for the routing engine.

Each matcher takes a context dict and returns True if its rule applies.
Matchers are referenced by dotted name in config/mappings.json (e.g. matchers.is_code_file).

Phase 1 will implement the individual matcher functions in this package.
"""
