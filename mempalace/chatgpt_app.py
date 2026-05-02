#!/usr/bin/env python3
"""Private ChatGPT Apps connector for MemPalace.

This is a separate Streamable HTTP MCP entrypoint for remote clients.  The
local stdio MCP server remains in :mod:`mempalace.mcp_server`.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from .version import __version__

logger = logging.getLogger("mempalace_chatgpt_app")

AUTH_SCOPE = "openid"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
UI_RESOURCE_URI = "ui://widget/mempalace.html"
MCP_POST_PATHS = {"/mcp", "/"}
UI_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MemPalace</title>
  <style>
    :root {
      color-scheme: light dark;
      --bg: #f7f8fb;
      --panel: #ffffff;
      --ink: #151923;
      --muted: #5a6475;
      --line: #d9dee8;
      --ok: #167b4b;
      --read: #255e9b;
      --write: #8a5a00;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --bg: #111318;
        --panel: #191d24;
        --ink: #eef2f7;
        --muted: #a8b1c0;
        --line: #2a303a;
        --ok: #5bc58d;
        --read: #7db7f1;
        --write: #e2ae4a;
      }
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font: 14px system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
    }
    main {
      display: grid;
      gap: 14px;
      min-height: 100vh;
      padding: 16px;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    h1 {
      margin: 0;
      font-size: 18px;
      line-height: 1.2;
      font-weight: 700;
      letter-spacing: 0;
    }
    .status {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      color: var(--ok);
      font-weight: 650;
      white-space: nowrap;
    }
    .dot {
      width: 9px;
      height: 9px;
      border-radius: 999px;
      background: var(--ok);
      box-shadow: 0 0 0 3px color-mix(in srgb, var(--ok) 18%, transparent);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }
    .metric, .tools {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 10px;
    }
    .label {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.2;
    }
    .value {
      margin-top: 4px;
      font-size: 15px;
      font-weight: 700;
      line-height: 1.2;
    }
    .tools {
      display: grid;
      gap: 8px;
    }
    .tool-row {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: center;
      min-height: 28px;
    }
    .tool-name {
      overflow-wrap: anywhere;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }
    .badge {
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 11px;
      font-weight: 700;
      line-height: 1.2;
      border: 1px solid currentColor;
    }
    .read { color: var(--read); }
    .write { color: var(--write); }
    @media (max-width: 420px) {
      main { padding: 12px; }
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>MemPalace</h1>
      <div class="status"><span class="dot"></span><span>Connected</span></div>
    </header>
    <section class="grid" aria-label="Connector status">
      <div class="metric"><div class="label">Mode</div><div class="value">Private</div></div>
      <div class="metric"><div class="label">Tools</div><div class="value">13</div></div>
      <div class="metric"><div class="label">Storage</div><div class="value">Local</div></div>
    </section>
    <section class="tools" aria-label="Available tools">
      <div class="tool-row"><span class="tool-name">status</span><span class="badge read">read</span></div>
      <div class="tool-row"><span class="tool-name">recall_context</span><span class="badge read">read</span></div>
      <div class="tool-row"><span class="tool-name">list_wings</span><span class="badge read">read</span></div>
      <div class="tool-row"><span class="tool-name">list_rooms</span><span class="badge read">read</span></div>
      <div class="tool-row"><span class="tool-name">search_memories</span><span class="badge read">read</span></div>
      <div class="tool-row"><span class="tool-name">get_drawer</span><span class="badge read">read</span></div>
      <div class="tool-row"><span class="tool-name">mempalace_kg_query</span><span class="badge read">read</span></div>
      <div class="tool-row"><span class="tool-name">remember_this</span><span class="badge write">write</span></div>
      <div class="tool-row"><span class="tool-name">add_memory</span><span class="badge write">write</span></div>
      <div class="tool-row"><span class="tool-name">update_drawer</span><span class="badge write">write</span></div>
      <div class="tool-row"><span class="tool-name">mempalace_diary_write</span><span class="badge write">write</span></div>
      <div class="tool-row"><span class="tool-name">mempalace_kg_add</span><span class="badge write">write</span></div>
      <div class="tool-row"><span class="tool-name">mempalace_kg_invalidate</span><span class="badge write">write</span></div>
    </section>
  </main>
</body>
</html>"""
_TOOLS_CACHE: dict[str, dict[str, Any]] | None = None


def _mcp_server():
    from . import mcp_server

    return mcp_server


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def public_base_url() -> str:
    return _env("MEMPALACE_CHATGPT_PUBLIC_URL", "https://mempalace-chatgpt.mjc.lol").rstrip("/")


def issuer_url() -> str:
    return _env("MEMPALACE_CHATGPT_OIDC_ISSUER", "https://auth.mjc.lol").rstrip("/")


def audiences() -> set[str]:
    configured = _env("MEMPALACE_CHATGPT_OIDC_AUDIENCE", public_base_url())
    return {item.strip() for item in configured.replace(",", " ").split() if item.strip()}


def jwks_url() -> str:
    configured = _env("MEMPALACE_CHATGPT_OIDC_JWKS_URL")
    if configured:
        return configured
    return f"{issuer_url()}/.well-known/jwks.json"


def resource_metadata_url() -> str:
    return f"{public_base_url()}/.well-known/oauth-protected-resource"


def _b64url_decode(value: str) -> bytes:
    value += "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _b64url_int(value: str) -> int:
    return int.from_bytes(_b64url_decode(value), "big")


def _json_b64url(value: str) -> dict[str, Any]:
    return json.loads(_b64url_decode(value).decode("utf-8"))


def _scope_set(claims: dict[str, Any]) -> set[str]:
    scopes = claims.get("scope", "")
    if isinstance(scopes, str):
        return {s for s in scopes.split() if s}
    if isinstance(scopes, list):
        return {str(s) for s in scopes}
    return set()


def _audience_matches(claim_aud: Any, expected: set[str]) -> bool:
    if isinstance(claim_aud, str):
        return claim_aud in expected
    if isinstance(claim_aud, list):
        return bool(expected.intersection(str(item) for item in claim_aud))
    return False


def _verify_rs256_signature(signing_input: bytes, signature: bytes, jwk: dict[str, Any]) -> bool:
    """Verify a JWT RS256 signature using only stdlib primitives."""
    if jwk.get("kty") != "RSA":
        return False
    n = _b64url_int(jwk["n"])
    e = _b64url_int(jwk["e"])
    k = (n.bit_length() + 7) // 8
    if len(signature) != k:
        return False

    digest_info = (
        bytes.fromhex("3031300d060960864801650304020105000420")
        + hashlib.sha256(signing_input).digest()
    )
    expected = b"\x00\x01" + (b"\xff" * (k - len(digest_info) - 3)) + b"\x00" + digest_info
    actual = pow(int.from_bytes(signature, "big"), e, n).to_bytes(k, "big")
    return actual == expected


class JwksVerifier:
    def __init__(
        self,
        jwks_uri: str,
        expected_issuer: str,
        expected_audiences: str | set[str],
        ttl: int = 300,
    ):
        self.jwks_uri = jwks_uri
        self.expected_issuer = expected_issuer
        if isinstance(expected_audiences, str):
            expected_audiences = {expected_audiences}
        self.expected_audiences = expected_audiences
        self.ttl = ttl
        self._jwks: dict[str, Any] | None = None
        self._jwks_until = 0.0

    def _load_jwks(self) -> dict[str, Any]:
        now = time.time()
        if self._jwks is not None and now < self._jwks_until:
            return self._jwks
        with urllib.request.urlopen(self.jwks_uri, timeout=10) as response:
            jwks = json.loads(response.read().decode("utf-8"))
        if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
            raise ValueError("JWKS response does not contain keys")
        self._jwks = jwks
        self._jwks_until = now + self.ttl
        return jwks

    def verify(self, token: str, required_scopes: set[str]) -> dict[str, Any]:
        try:
            header_part, payload_part, signature_part = token.split(".")
        except ValueError as exc:
            raise ValueError("Bearer token is not a JWT") from exc

        header = _json_b64url(header_part)
        claims = _json_b64url(payload_part)
        if header.get("alg") != "RS256":
            raise ValueError("Only RS256 JWTs are accepted")

        key_id = header.get("kid")
        keys = self._load_jwks().get("keys", [])
        jwk = next((key for key in keys if key.get("kid") == key_id), None)
        if jwk is None:
            raise ValueError("JWT key id is not in JWKS")

        signing_input = f"{header_part}.{payload_part}".encode("ascii")
        signature = _b64url_decode(signature_part)
        if not _verify_rs256_signature(signing_input, signature, jwk):
            raise ValueError("JWT signature is invalid")

        now = int(time.time())
        if claims.get("iss") != self.expected_issuer:
            raise ValueError("JWT issuer is invalid")
        if not _audience_matches(claims.get("aud"), self.expected_audiences):
            raise ValueError("JWT audience is invalid")
        if int(claims.get("exp", 0)) <= now:
            raise ValueError("JWT is expired")
        if "nbf" in claims and int(claims["nbf"]) > now:
            raise ValueError("JWT is not valid yet")

        token_scopes = _scope_set(claims)
        if token_scopes:
            missing = required_scopes - token_scopes
            if missing:
                raise PermissionError(
                    f"JWT is missing required scope(s): {', '.join(sorted(missing))}"
                )
        return claims


def _read_scheme() -> dict[str, Any]:
    return {"type": "oauth2", "scopes": [AUTH_SCOPE]}


def _write_scheme() -> dict[str, Any]:
    return {"type": "oauth2", "scopes": [AUTH_SCOPE]}


def _tool(
    title: str,
    description: str,
    input_schema: dict[str, Any],
    handler: Any,
    scopes: set[str],
    read_only: bool = True,
    destructive: bool = False,
) -> dict[str, Any]:
    return {
        "title": title,
        "description": description,
        "input_schema": input_schema,
        "handler": handler,
        "required_scopes": scopes,
        "securitySchemes": [_read_scheme() if read_only else _write_scheme()],
        "annotations": {
            "readOnlyHint": read_only,
            "destructiveHint": destructive,
            "idempotentHint": read_only,
            "openWorldHint": False,
        },
    }


def _handle_recall_context(
    query: str,
    limit: int = 5,
    wing: str | None = None,
    room: str | None = None,
    context: str | None = None,
):
    """Memory-shaped search wrapper for ChatGPT's routine context recall."""
    result = _mcp_server().tool_search(
        query=query,
        limit=limit,
        wing=wing,
        room=room,
        max_distance=1.5,
        context=context,
    )
    if isinstance(result, dict):
        result.setdefault(
            "usage",
            "Use drawer_id with get_drawer when more full verbatim content is needed.",
        )
    return result


def _handle_remember_this(
    content: str,
    wing: str = "chatgpt",
    room: str = "inbox",
    source_file: str = "chatgpt://memory",
):
    """Store durable ChatGPT memory as exact user-provided content."""
    return _mcp_server().tool_add_drawer(
        wing=wing,
        room=room,
        content=content,
        source_file=source_file or "chatgpt://memory",
        added_by="chatgpt",
    )


def chatgpt_tools() -> dict[str, dict[str, Any]]:
    global _TOOLS_CACHE
    if _TOOLS_CACHE is not None:
        return _TOOLS_CACHE

    mcp_server = _mcp_server()
    _TOOLS_CACHE = {
        "status": _tool(
            "Status",
            "Return MemPalace status, counts, palace path, and protocol information.",
            {"type": "object", "properties": {}},
            mcp_server.tool_status,
            {AUTH_SCOPE},
        ),
        "recall_context": _tool(
            "Recall context",
            (
                "Use before answering questions about prior conversations, user preferences, "
                "projects, people, decisions, remembered facts, or anything that may depend on "
                "memory. Returns verbatim MemPalace drawers with drawer_id values."
            ),
            {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Short memory search keywords or question.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of memories to return.",
                        "default": 5,
                    },
                    "wing": {"type": "string", "description": "Optional wing filter."},
                    "room": {"type": "string", "description": "Optional room filter."},
                    "context": {
                        "type": "string",
                        "description": "Optional background context for reranking, not embedding.",
                    },
                },
                "required": ["query"],
            },
            _handle_recall_context,
            {AUTH_SCOPE},
        ),
        "list_wings": _tool(
            "List wings",
            "List all MemPalace wings with drawer counts.",
            {"type": "object", "properties": {}},
            mcp_server.tool_list_wings,
            {AUTH_SCOPE},
        ),
        "list_rooms": _tool(
            "List rooms",
            "List rooms within a wing, or all rooms if no wing is provided.",
            mcp_server.TOOLS["mempalace_list_rooms"]["input_schema"],
            mcp_server.tool_list_rooms,
            {AUTH_SCOPE},
        ),
        "search_memories": _tool(
            "Search memories",
            "Search MemPalace and return verbatim drawer content with scores.",
            mcp_server.TOOLS["mempalace_search"]["input_schema"],
            mcp_server.tool_search,
            {AUTH_SCOPE},
        ),
        "get_drawer": _tool(
            "Get drawer",
            "Fetch one drawer by ID, including full verbatim content and metadata.",
            mcp_server.TOOLS["mempalace_get_drawer"]["input_schema"],
            mcp_server.tool_get_drawer,
            {AUTH_SCOPE},
        ),
        "mempalace_kg_query": _tool(
            "Query knowledge graph",
            (
                "Query typed MemPalace knowledge graph facts for an entity before answering "
                "questions about people, projects, relationships, preferences, or facts that "
                "may have changed over time."
            ),
            mcp_server.TOOLS["mempalace_kg_query"]["input_schema"],
            mcp_server.tool_kg_query,
            {AUTH_SCOPE},
        ),
        "remember_this": _tool(
            "Remember this",
            (
                "Use when the user states durable preferences, project facts, personal facts, "
                "decisions, corrections, or anything they ask to remember. Stores the exact "
                "verbatim content."
            ),
            {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Exact verbatim content to store, never summarized.",
                    },
                    "wing": {
                        "type": "string",
                        "description": "Optional wing; defaults to chatgpt.",
                        "default": "chatgpt",
                    },
                    "room": {
                        "type": "string",
                        "description": "Optional room; defaults to inbox.",
                        "default": "inbox",
                    },
                    "source_file": {
                        "type": "string",
                        "description": "Optional source label; defaults to chatgpt://memory.",
                        "default": "chatgpt://memory",
                    },
                },
                "required": ["content"],
            },
            _handle_remember_this,
            {AUTH_SCOPE},
            read_only=False,
        ),
        "add_memory": _tool(
            "Add memory",
            "File verbatim content into a MemPalace wing and room.",
            {
                "type": "object",
                "properties": {
                    "wing": {"type": "string", "description": "Wing to store the memory in"},
                    "room": {"type": "string", "description": "Room to store the memory in"},
                    "content": {
                        "type": "string",
                        "description": "Exact verbatim content to store, never summarized",
                    },
                    "source_file": {"type": "string", "description": "Optional source label"},
                },
                "required": ["wing", "room", "content"],
            },
            mcp_server.tool_add_drawer,
            {AUTH_SCOPE},
            read_only=False,
        ),
        "update_drawer": _tool(
            "Update drawer",
            "Update an existing drawer's verbatim content or wing/room metadata.",
            mcp_server.TOOLS["mempalace_update_drawer"]["input_schema"],
            mcp_server.tool_update_drawer,
            {AUTH_SCOPE},
            read_only=False,
        ),
        "mempalace_diary_write": _tool(
            "Write diary",
            (
                "Write a compact agent diary entry about this ChatGPT session, decisions made, "
                "facts learned, debugging outcomes, and follow-up state. Preserve meaningful "
                "details; do not use this for secrets."
            ),
            mcp_server.TOOLS["mempalace_diary_write"]["input_schema"],
            mcp_server.tool_diary_write,
            {AUTH_SCOPE},
            read_only=False,
        ),
        "mempalace_kg_add": _tool(
            "Add knowledge graph fact",
            (
                "Add a typed subject-predicate-object fact to the MemPalace knowledge graph "
                "when the user states a durable relationship, preference, project fact, or "
                "personal fact."
            ),
            mcp_server.TOOLS["mempalace_kg_add"]["input_schema"],
            mcp_server.tool_kg_add,
            {AUTH_SCOPE},
            read_only=False,
        ),
        "mempalace_kg_invalidate": _tool(
            "Invalidate knowledge graph fact",
            (
                "Mark a previously true knowledge graph fact as no longer true when the user "
                "corrects or updates a relationship, status, preference, or project fact."
            ),
            mcp_server.TOOLS["mempalace_kg_invalidate"]["input_schema"],
            mcp_server.tool_kg_invalidate,
            {AUTH_SCOPE},
            read_only=False,
            destructive=True,
        ),
    }
    return _TOOLS_CACHE


def oauth_resource_metadata() -> dict[str, Any]:
    return {
        "resource": public_base_url(),
        "authorization_servers": [issuer_url()],
        "scopes_supported": [AUTH_SCOPE],
        "resource_documentation": f"{public_base_url()}/",
        "token_endpoint_auth_methods_supported": [
            "none",
            "client_secret_post",
            "client_secret_basic",
        ],
    }


def _www_authenticate(scopes: set[str], error: str = "insufficient_scope") -> str:
    scope = " ".join(sorted(scopes))
    return (
        f'Bearer resource_metadata="{resource_metadata_url()}", '
        f'error="{error}", '
        f'error_description="Link MemPalace to continue", '
        f'scope="{scope}"'
    )


def auth_error_result(
    req_id: Any, scopes: set[str], message: str = "Authentication required"
) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "content": [{"type": "text", "text": message}],
            "_meta": {"mcp/www_authenticate": [_www_authenticate(scopes)]},
            "isError": True,
        },
    }


def auth_error_headers(scopes: set[str]) -> dict[str, str]:
    return {"WWW-Authenticate": _www_authenticate(scopes)}


def _tool_descriptor(name: str, tool: dict[str, Any]) -> dict[str, Any]:
    descriptor = {
        "name": name,
        "title": tool["title"],
        "description": tool["description"],
        "inputSchema": tool["input_schema"],
        "securitySchemes": tool["securitySchemes"],
        "annotations": tool["annotations"],
        "_meta": {"securitySchemes": tool["securitySchemes"]},
    }
    if name == "status":
        descriptor["_meta"]["ui"] = {"resourceUri": UI_RESOURCE_URI}
    return descriptor


def _coerce_args(tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    schema_props = tool["input_schema"].get("properties", {})
    coerced = {k: v for k, v in (args or {}).items() if k in schema_props}
    for key, value in list(coerced.items()):
        declared_type = schema_props.get(key, {}).get("type")
        if declared_type == "integer" and not isinstance(value, int):
            coerced[key] = int(value)
        elif declared_type == "number" and not isinstance(value, (int, float)):
            coerced[key] = float(value)
    return coerced


def handle_mcp_request(
    request: dict[str, Any], claims: dict[str, Any] | None = None
) -> dict | None:
    if not isinstance(request, dict):
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": "Invalid Request"},
        }

    method = request.get("method") or ""
    params = request.get("params") or {}
    req_id = request.get("id")

    if method == "initialize":
        result = _mcp_server().handle_request(request)
        if result and "result" in result:
            result["result"]["serverInfo"] = {"name": "mempalace-chatgpt", "version": __version__}
            result["result"]["capabilities"] = {"tools": {}, "resources": {}}
        return result
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method.startswith("notifications/"):
        return None
    if method == "tools/list":
        tools = chatgpt_tools()
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": [_tool_descriptor(name, tool) for name, tool in tools.items()]},
        }
    if method == "resources/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "resources": [
                    {
                        "uri": UI_RESOURCE_URI,
                        "name": "MemPalace",
                        "title": "MemPalace",
                        "mimeType": "text/html",
                        "description": "Private MemPalace connector widget.",
                    }
                ]
            },
        }
    if method == "resources/read":
        uri = params.get("uri") if isinstance(params, dict) else None
        if uri != UI_RESOURCE_URI:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": f"Unknown resource: {uri}"},
            }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "contents": [
                    {
                        "uri": UI_RESOURCE_URI,
                        "mimeType": "text/html",
                        "text": UI_HTML,
                    }
                ]
            },
        }
    if method == "tools/call":
        if not isinstance(params, dict) or "name" not in params:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32600, "message": "Invalid Request"},
            }
        name = params.get("name")
        tools = chatgpt_tools()
        if name not in tools:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {name}"},
            }
        tool = tools[name]
        try:
            args = _coerce_args(tool, params.get("arguments") or {})
        except (TypeError, ValueError) as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": str(exc)},
            }
        try:
            result = tool["handler"](**args)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                    "structuredContent": result if isinstance(result, dict) else {},
                },
            }
        except Exception:
            logger.exception("Tool error in %s", name)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": "Internal tool error"},
            }

    if req_id is None:
        return None
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }


class ChatGptMcpHandler(BaseHTTPRequestHandler):
    server_version = "MemPalaceChatGPT/1"

    def _send_json(
        self, status: int, payload: dict[str, Any], headers: dict[str, str] | None = None
    ):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, status: int, html: str):
        data = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Headers", "Authorization, Content-Type, MCP-Protocol-Version"
        )
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/.well-known/oauth-protected-resource":
            self._send_json(200, oauth_resource_metadata())
            return
        if path in ("/", "/ui"):
            self._send_html(200, UI_HTML)
            return
        if path == "/health":
            self._send_json(200, {"ok": True, "version": __version__})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in MCP_POST_PATHS:
            self._send_json(404, {"error": "not found"})
            return
        content_type = self.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            self._send_json(415, {"error": "Content-Type must be application/json"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        try:
            request = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json(
                400,
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
            )
            return

        scopes = _required_scopes_for_request(request)
        verifier: JwksVerifier = self.server.verifier  # type: ignore[attr-defined]
        token = _bearer_token(self.headers.get("Authorization", ""))
        claims = None
        try:
            if scopes:
                if not token:
                    raise PermissionError("missing bearer token")
                claims = verifier.verify(token, scopes)
        except (PermissionError, ValueError, urllib.error.URLError) as exc:
            logger.info("MCP auth failed: %s", exc)
            self._send_json(
                200,
                auth_error_result(request.get("id"), scopes),
                headers=auth_error_headers(scopes),
            )
            return

        response = handle_mcp_request(request, claims=claims)
        if response is None:
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._send_json(200, response)


def _bearer_token(header: str) -> str:
    prefix = "Bearer "
    if header.startswith(prefix):
        return header[len(prefix) :].strip()
    return ""


def _required_scopes_for_request(request: dict[str, Any]) -> set[str]:
    method = request.get("method") if isinstance(request, dict) else None
    if method == "tools/list":
        return set()
    if method in ("resources/list", "resources/read"):
        return set()
    if method == "tools/call":
        params = request.get("params") or {}
        if isinstance(params, dict):
            tool = chatgpt_tools().get(params.get("name"))
            if tool:
                return set(tool["required_scopes"])
        return {AUTH_SCOPE}
    if method in ("initialize", "ping") or (
        isinstance(method, str) and method.startswith("notifications/")
    ):
        return set()
    return {AUTH_SCOPE}


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    verifier = JwksVerifier(jwks_url(), issuer_url(), audiences())
    server = ThreadingHTTPServer((host, port), ChatGptMcpHandler)
    server.verifier = verifier  # type: ignore[attr-defined]
    logger.info("MemPalace ChatGPT MCP app listening on http://%s:%s/mcp", host, port)
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="MemPalace ChatGPT Apps MCP server")
    parser.add_argument("--host", default=_env("MEMPALACE_CHATGPT_HOST", DEFAULT_HOST))
    parser.add_argument(
        "--port", type=int, default=int(_env("MEMPALACE_CHATGPT_PORT", str(DEFAULT_PORT)))
    )
    args = parser.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
