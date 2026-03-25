"""Routing handler stubs — real logic added later with reference material.

Handler contract: handler(tool_name: str, tool_input: dict) -> dict | None
Returns a dict logged as handler_output, or None. Exceptions are caught by
the router and logged; the routing decision is still recorded.
"""


def route_read_code(tool_name: str, tool_input: dict) -> dict | None:
    """Redirect Read calls on code files to jCodeMunch (stub)."""
    return None


def route_read_doc(tool_name: str, tool_input: dict) -> dict | None:
    """Redirect Read calls on doc files to jDocMunch (stub)."""
    return None


def redirect_to_exa(tool_name: str, tool_input: dict) -> dict | None:
    """Redirect WebSearch calls to Exa MCP (stub)."""
    return None
