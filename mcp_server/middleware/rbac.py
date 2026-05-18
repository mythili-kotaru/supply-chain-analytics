"""
mcp_server/middleware/rbac.py
──────────────────────────────
RBAC (Role-Based Access Control) middleware for FastMCP.

CONCEPT: What is middleware?
Middleware is code that runs BETWEEN the HTTP request arriving and your
tool function executing. It can inspect, modify, or reject the request.

Think of it like a security guard: every visitor (request) passes through
the guard before entering the building (tool function).

In FastMCP, middleware is a Starlette middleware class because FastMCP
is built on Starlette (same as FastAPI under the hood).

HOW RBAC WORKS HERE:
  1. Every request includes an 'x-role' header: 'analyst' or 'admin'
  2. Middleware extracts the role and injects it into the tool call context
  3. Each tool calls require_role() to check if the caller has permission
  4. If not → raises ToolError (MCP's error type) → client sees an error

IN PRODUCTION:
  The 'x-role' header would be replaced with a JWT.
  The middleware would verify the JWT signature with a public key,
  extract the role from claims, and inject it. Same pattern, more security.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastmcp.exceptions import ToolError


# ─────────────────────────────────────────────
# ROLE DEFINITIONS
#
# WHY a dict and not if/elif?
# Easier to extend. Adding a new role = adding one dict entry.
# Also, set operations (ALLOWED_TOOLS[role] & requested_tool) are O(1).
# ─────────────────────────────────────────────
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "analyst": {
        "hybrid_search",
        "inventory_lookup",
        "entity_resolve",
        # NOT submit_recommendation — analysts are read-only
    },
    "admin": {
        "hybrid_search",
        "inventory_lookup",
        "entity_resolve",
        "submit_recommendation",   # admins can write
    }
}

VALID_ROLES = set(ROLE_PERMISSIONS.keys())


class RBACMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that extracts and validates the caller's role.

    It doesn't enforce per-tool permissions here (that happens in require_role()).
    This middleware's job is simpler: make the role available on the request state
    so tool functions can read it.

    WHY BaseHTTPMiddleware?
    FastMCP is a Starlette app. Starlette middleware intercepts at the HTTP level,
    before FastMCP's routing logic processes the request.
    """

    async def dispatch(self, request: Request, call_next):
        # Extract role from header (default to 'analyst' if missing)
        role = request.headers.get("x-role", "analyst").lower().strip()

        # Validate role
        if role not in VALID_ROLES:
            # Return 403 immediately — don't even reach the tool
            return JSONResponse(
                {"error": f"Invalid role '{role}'. Must be one of: {sorted(VALID_ROLES)}"},
                status_code=403
            )

        # Inject into request state — tools can read request.state.role
        # (FastMCP passes this through to the tool context)
        request.state.role = role

        # Continue to the next middleware / route handler
        response = await call_next(request)
        return response


def require_role(role: str, allowed: list[str]) -> None:
    """
    Assert that the caller's role is in the allowed list.
    Called inside tool functions to enforce per-tool permission.

    Args:
        role: The role from the request (injected by middleware or tool parameter)
        allowed: List of roles that may call this tool

    Raises:
        ToolError: MCP's standard error type — propagates back to the client
                   as a structured error response.

    Example:
        require_role(role, allowed=["admin"])
        # If role == "analyst" → raises ToolError("Permission denied...")
    """
    if role not in allowed:
        raise ToolError(
            f"Permission denied: role '{role}' cannot call this tool. "
            f"Required: one of {allowed}."
        )
