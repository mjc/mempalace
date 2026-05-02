import base64
import hashlib
import json
import random
import time

import pytest

from mempalace import chatgpt_app


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _is_probable_prime(n: int) -> bool:
    if n < 2:
        return False
    small_primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37]
    if any(n == p for p in small_primes):
        return True
    if any(n % p == 0 for p in small_primes):
        return False
    d = n - 1
    s = 0
    while d % 2 == 0:
        s += 1
        d //= 2
    for a in [2, 3, 5, 7, 11, 13, 17]:
        if a >= n:
            continue
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime(rng: random.Random, bits: int) -> int:
    while True:
        value = rng.getrandbits(bits) | (1 << (bits - 1)) | 1
        if _is_probable_prime(value):
            return value


def _rsa_fixture():
    rng = random.Random(42)
    e = 65537
    while True:
        p = _prime(rng, 512)
        q = _prime(rng, 512)
        phi = (p - 1) * (q - 1)
        if phi % e != 0:
            break
    n = p * q
    d = pow(e, -1, phi)
    jwk = {
        "kty": "RSA",
        "kid": "test-key",
        "alg": "RS256",
        "n": _b64url(n.to_bytes((n.bit_length() + 7) // 8, "big")),
        "e": _b64url(e.to_bytes((e.bit_length() + 7) // 8, "big")),
    }
    return n, d, jwk


def _jwt(n, d, claims):
    header = {"alg": "RS256", "kid": "test-key", "typ": "JWT"}
    header_part = _b64url(json.dumps(header, separators=(",", ":")).encode())
    payload_part = _b64url(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{header_part}.{payload_part}".encode("ascii")
    digest_info = (
        bytes.fromhex("3031300d060960864801650304020105000420")
        + hashlib.sha256(signing_input).digest()
    )
    k = (n.bit_length() + 7) // 8
    encoded = b"\x00\x01" + (b"\xff" * (k - len(digest_info) - 3)) + b"\x00" + digest_info
    signature = pow(int.from_bytes(encoded, "big"), d, n).to_bytes(k, "big")
    return f"{header_part}.{payload_part}.{_b64url(signature)}"


def test_tool_list_is_chatgpt_v1_surface_only():
    response = chatgpt_app.handle_mcp_request({"method": "tools/list", "id": 1, "params": {}})
    tools = response["result"]["tools"]
    names = {tool["name"] for tool in tools}

    assert names == {
        "recall_context",
        "search_memories",
        "get_drawer",
        "list_wings",
        "list_rooms",
        "status",
        "mempalace_kg_query",
        "remember_this",
        "add_memory",
        "update_drawer",
        "mempalace_diary_write",
        "mempalace_kg_add",
        "mempalace_kg_invalidate",
    }
    assert "mempalace_delete_drawer" not in names
    assert "mempalace_create_tunnel" not in names

    search = next(tool for tool in tools if tool["name"] == "search_memories")
    recall = next(tool for tool in tools if tool["name"] == "recall_context")
    kg_query = next(tool for tool in tools if tool["name"] == "mempalace_kg_query")
    remember = next(tool for tool in tools if tool["name"] == "remember_this")
    kg_invalidate = next(tool for tool in tools if tool["name"] == "mempalace_kg_invalidate")
    add = next(tool for tool in tools if tool["name"] == "add_memory")
    assert search["annotations"]["readOnlyHint"] is True
    assert recall["annotations"]["readOnlyHint"] is True
    assert "prior conversations" in recall["description"]
    assert kg_query["annotations"]["readOnlyHint"] is True
    assert "knowledge graph facts" in kg_query["description"]
    assert remember["annotations"]["readOnlyHint"] is False
    assert "exact verbatim content" in remember["description"]
    assert kg_invalidate["annotations"]["readOnlyHint"] is False
    assert kg_invalidate["annotations"]["destructiveHint"] is True
    assert add["annotations"]["readOnlyHint"] is False
    assert add["securitySchemes"] == [{"type": "oauth2", "scopes": ["openid"]}]
    assert add["_meta"]["securitySchemes"] == add["securitySchemes"]


def test_initialize_and_resources_advertise_iframe_ui():
    init = chatgpt_app.handle_mcp_request({"method": "initialize", "id": 1, "params": {}})
    assert "resources" in init["result"]["capabilities"]

    listed = chatgpt_app.handle_mcp_request({"method": "resources/list", "id": 2, "params": {}})
    resource = listed["result"]["resources"][0]
    assert resource["uri"] == chatgpt_app.UI_RESOURCE_URI
    assert resource["mimeType"] == "text/html"

    read = chatgpt_app.handle_mcp_request(
        {"method": "resources/read", "id": 3, "params": {"uri": chatgpt_app.UI_RESOURCE_URI}}
    )
    content = read["result"]["contents"][0]
    assert content["text"].startswith("<!doctype html>")
    assert "Connected" in content["text"]
    assert "recall_context" in content["text"]
    assert "search_memories" in content["text"]
    assert "remember_this" in content["text"]
    assert "add_memory" in content["text"]
    assert "mempalace_diary_write" in content["text"]
    assert "mempalace_kg_query" in content["text"]


def test_recall_context_wraps_search_with_drawer_ids(monkeypatch):
    chatgpt_app._TOOLS_CACHE = None
    calls = []

    def fake_search(**kwargs):
        calls.append(kwargs)
        return {
            "query": kwargs["query"],
            "results": [
                {
                    "drawer_id": "drawer_projects_diary_123",
                    "content": "verbatim memory",
                }
            ],
        }

    monkeypatch.setattr(chatgpt_app._mcp_server(), "tool_search", fake_search)

    response = chatgpt_app.handle_mcp_request(
        {
            "method": "tools/call",
            "id": 9,
            "params": {
                "name": "recall_context",
                "arguments": {
                    "query": "HASS_TOKEN",
                    "limit": "3",
                    "wing": "projects",
                    "room": "diary",
                    "context": "debugging a stale drawer",
                },
            },
        },
        claims={"sub": "user"},
    )

    assert calls == [
        {
            "query": "HASS_TOKEN",
            "limit": 3,
            "wing": "projects",
            "room": "diary",
            "max_distance": 1.5,
            "context": "debugging a stale drawer",
        }
    ]
    structured = response["result"]["structuredContent"]
    assert structured["results"][0]["drawer_id"] == "drawer_projects_diary_123"
    assert "get_drawer" in structured["usage"]


def test_remember_this_files_verbatim_content_with_defaults(monkeypatch):
    chatgpt_app._TOOLS_CACHE = None
    calls = []

    def fake_add_drawer(**kwargs):
        calls.append(kwargs)
        return {"success": True, "drawer_id": "drawer_chatgpt_inbox_123"}

    monkeypatch.setattr(chatgpt_app._mcp_server(), "tool_add_drawer", fake_add_drawer)

    response = chatgpt_app.handle_mcp_request(
        {
            "method": "tools/call",
            "id": 10,
            "params": {
                "name": "remember_this",
                "arguments": {"content": "HASS_TOKEN is what I meant."},
            },
        },
        claims={"sub": "user"},
    )

    assert calls == [
        {
            "wing": "chatgpt",
            "room": "inbox",
            "content": "HASS_TOKEN is what I meant.",
            "source_file": "chatgpt://memory",
            "added_by": "chatgpt",
        }
    ]
    assert response["result"]["structuredContent"]["success"] is True


def test_advanced_protocol_tools_forward_to_mcp_server(monkeypatch):
    chatgpt_app._TOOLS_CACHE = None
    calls = []
    mcp_server = chatgpt_app._mcp_server()

    def fake_kg_query(**kwargs):
        calls.append(("kg_query", kwargs))
        return {"entity": kwargs["entity"], "facts": [{"predicate": "works_on"}], "count": 1}

    def fake_diary_write(**kwargs):
        calls.append(("diary_write", kwargs))
        return {"success": True, "entry_id": "diary_chatgpt_123"}

    def fake_kg_add(**kwargs):
        calls.append(("kg_add", kwargs))
        return {"success": True, "triple_id": 42}

    def fake_kg_invalidate(**kwargs):
        calls.append(("kg_invalidate", kwargs))
        return {"success": True}

    monkeypatch.setattr(mcp_server, "tool_kg_query", fake_kg_query)
    monkeypatch.setattr(mcp_server, "tool_diary_write", fake_diary_write)
    monkeypatch.setattr(mcp_server, "tool_kg_add", fake_kg_add)
    monkeypatch.setattr(mcp_server, "tool_kg_invalidate", fake_kg_invalidate)

    requests = [
        (
            "mempalace_kg_query",
            {"entity": "MemPalace", "direction": "both"},
            {"entity": "MemPalace", "direction": "both"},
        ),
        (
            "mempalace_diary_write",
            {"agent_name": "chatgpt", "entry": "SESSION:test", "topic": "deploy"},
            {"agent_name": "chatgpt", "entry": "SESSION:test", "topic": "deploy"},
        ),
        (
            "mempalace_kg_add",
            {"subject": "MemPalace", "predicate": "has_tool", "object": "kg_query"},
            {"subject": "MemPalace", "predicate": "has_tool", "object": "kg_query"},
        ),
        (
            "mempalace_kg_invalidate",
            {
                "subject": "MemPalace",
                "predicate": "missing_tool",
                "object": "kg_query",
                "ended": "2026-05-01",
            },
            {
                "subject": "MemPalace",
                "predicate": "missing_tool",
                "object": "kg_query",
                "ended": "2026-05-01",
            },
        ),
    ]

    for i, (name, arguments, _expected) in enumerate(requests, start=20):
        response = chatgpt_app.handle_mcp_request(
            {
                "method": "tools/call",
                "id": i,
                "params": {"name": name, "arguments": arguments},
            },
            claims={"sub": "user"},
        )
        assert "structuredContent" in response["result"]

    assert calls == [
        ("kg_query", requests[0][2]),
        ("diary_write", requests[1][2]),
        ("kg_add", requests[2][2]),
        ("kg_invalidate", requests[3][2]),
    ]


def test_oauth_resource_metadata(monkeypatch):
    monkeypatch.setenv("MEMPALACE_CHATGPT_PUBLIC_URL", "https://mempalace-chatgpt.mjc.lol")
    monkeypatch.setenv("MEMPALACE_CHATGPT_OIDC_ISSUER", "https://auth.mjc.lol")

    metadata = chatgpt_app.oauth_resource_metadata()

    assert metadata["resource"] == "https://mempalace-chatgpt.mjc.lol"
    assert metadata["authorization_servers"] == ["https://auth.mjc.lol"]
    assert metadata["scopes_supported"] == ["openid"]


def test_audiences_parses_space_and_comma_separated_values(monkeypatch):
    monkeypatch.setenv(
        "MEMPALACE_CHATGPT_OIDC_AUDIENCE",
        "https://mempalace-chatgpt.mjc.lol, 22ae7c1d-b7bd-44f6-9ecb-572d668f2170",
    )

    assert chatgpt_app.audiences() == {
        "https://mempalace-chatgpt.mjc.lol",
        "22ae7c1d-b7bd-44f6-9ecb-572d668f2170",
    }


def test_root_post_is_accepted_as_mcp_alias():
    assert chatgpt_app.MCP_POST_PATHS == {"/mcp", "/"}


def test_auth_error_result_contains_mcp_www_authenticate(monkeypatch):
    monkeypatch.setenv("MEMPALACE_CHATGPT_PUBLIC_URL", "https://mempalace-chatgpt.mjc.lol")

    response = chatgpt_app.auth_error_result(4, {"openid"})
    headers = chatgpt_app.auth_error_headers({"openid"})

    result = response["result"]
    challenge = result["_meta"]["mcp/www_authenticate"][0]
    assert result["isError"] is True
    assert (
        'resource_metadata="https://mempalace-chatgpt.mjc.lol/.well-known/oauth-protected-resource"'
        in challenge
    )
    assert 'error="insufficient_scope"' in challenge
    assert headers["WWW-Authenticate"] == challenge


def test_jwt_verifier_accepts_valid_token():
    n, d, jwk = _rsa_fixture()
    verifier = chatgpt_app.JwksVerifier(
        "memory://jwks", "https://auth.example", "mempalace-chatgpt"
    )
    verifier._jwks = {"keys": [jwk]}
    verifier._jwks_until = time.time() + 60
    token = _jwt(
        n,
        d,
        {
            "iss": "https://auth.example",
            "aud": "mempalace-chatgpt",
            "exp": int(time.time()) + 60,
            "scope": "openid profile email groups",
        },
    )

    claims = verifier.verify(token, {"openid"})

    assert claims["aud"] == "mempalace-chatgpt"


def test_jwt_verifier_accepts_any_configured_audience():
    n, d, jwk = _rsa_fixture()
    verifier = chatgpt_app.JwksVerifier(
        "memory://jwks", "https://auth.example", {"resource-url", "client-id"}
    )
    verifier._jwks = {"keys": [jwk]}
    verifier._jwks_until = time.time() + 60
    token = _jwt(
        n,
        d,
        {
            "iss": "https://auth.example",
            "aud": "client-id",
            "exp": int(time.time()) + 60,
            "scope": "openid",
        },
    )

    claims = verifier.verify(token, {"openid"})

    assert claims["aud"] == "client-id"


def test_jwt_verifier_accepts_pocket_id_token_without_scope_claim():
    n, d, jwk = _rsa_fixture()
    verifier = chatgpt_app.JwksVerifier(
        "memory://jwks", "https://auth.example", {"resource-url", "client-id"}
    )
    verifier._jwks = {"keys": [jwk]}
    verifier._jwks_until = time.time() + 60
    token = _jwt(
        n,
        d,
        {
            "iss": "https://auth.example",
            "aud": "client-id",
            "exp": int(time.time()) + 60,
        },
    )

    claims = verifier.verify(token, {"openid"})

    assert claims["aud"] == "client-id"


@pytest.mark.parametrize(
    "claims,error",
    [
        ({"iss": "https://wrong.example", "aud": "mempalace-chatgpt"}, "issuer"),
        ({"iss": "https://auth.example", "aud": "wrong-audience"}, "audience"),
        ({"iss": "https://auth.example", "aud": "mempalace-chatgpt", "exp": 1}, "expired"),
    ],
)
def test_jwt_verifier_rejects_bad_claims(claims, error):
    n, d, jwk = _rsa_fixture()
    verifier = chatgpt_app.JwksVerifier(
        "memory://jwks", "https://auth.example", "mempalace-chatgpt"
    )
    verifier._jwks = {"keys": [jwk]}
    verifier._jwks_until = time.time() + 60
    full_claims = {
        "exp": int(time.time()) + 60,
        "scope": "openid",
        **claims,
    }
    token = _jwt(n, d, full_claims)

    with pytest.raises(ValueError, match=error):
        verifier.verify(token, {"openid"})


def test_jwt_verifier_rejects_missing_scope():
    n, d, jwk = _rsa_fixture()
    verifier = chatgpt_app.JwksVerifier(
        "memory://jwks", "https://auth.example", "mempalace-chatgpt"
    )
    verifier._jwks = {"keys": [jwk]}
    verifier._jwks_until = time.time() + 60
    token = _jwt(
        n,
        d,
        {
            "iss": "https://auth.example",
            "aud": "mempalace-chatgpt",
            "exp": int(time.time()) + 60,
            "scope": "openid",
        },
    )

    with pytest.raises(PermissionError, match="missing required scope"):
        verifier.verify(token, {"openid", "email"})
