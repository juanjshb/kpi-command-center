from datetime import timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import create_access_token, decode_token, verify_password
from app.db.base import utcnow
from app.models.enums import Role


def test_login_profile_and_claims(client, data):
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "ADMIN@EXAMPLE.COM", "password": "Valid-password-123"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    payload = decode_token(token)
    assert payload["sub"] == str(data["users"]["ADMIN"].id)
    assert payload["role"] == "ADMIN"
    assert response.json()["expires_in"] == 2700
    profile = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert profile.status_code == 200
    assert "hashed_password" not in profile.text
    assert response.headers["cache-control"] == "no-store"
    assert data["users"]["ADMIN"].hashed_password.startswith("$2")


@pytest.mark.parametrize(
    "path",
    [
        "/atms",
        "/branches",
        "/incidents",
        "/metrics/summary",
        "/geo/locations",
        "/users",
        "/competitors/comparison",
    ],
)
def test_requires_auth(client, path):
    assert client.get("/api/v1" + path).status_code == 401


@pytest.mark.parametrize(
    "corruption", ["expired", "signature", "sub", "aud", "type", "missing_exp"]
)
def test_invalid_tokens(client, data, corruption):
    payload = decode_token(create_access_token(data["users"]["ADMIN"]))
    key = get_settings().secret_key.get_secret_value()
    if corruption == "expired":
        payload["exp"] = utcnow() - timedelta(seconds=10)
    elif corruption == "signature":
        key = "incorrect-key" * 4
    elif corruption == "sub":
        payload["sub"] = "not-a-uuid"
    elif corruption == "aud":
        payload["aud"] = "other-api"
    elif corruption == "type":
        payload["type"] = "refresh"
    else:
        del payload["exp"]
    token = jwt.encode(payload, key, algorithm="HS256")
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token}).status_code
        == 401
    )


def test_rbac_and_role_read_from_db(client, headers, data, db):
    assert client.get("/api/v1/atms", headers=headers["ANALYST"]).status_code == 200
    target = data["atms"][0].id
    assert (
        client.patch(
            f"/api/v1/atms/{target}/status",
            json={"nivel_efectivo_pct": 80},
            headers=headers["ANALYST"],
        ).status_code
        == 403
    )
    assert client.get("/api/v1/users", headers=headers["OPERATOR"]).status_code == 403
    data["users"]["ADMIN"].role = Role.ANALYST
    db.commit()
    assert client.get("/api/v1/users", headers=headers["ADMIN"]).status_code == 403


def test_logout_revokes_token(client, headers):
    assert client.post("/api/v1/auth/logout", headers=headers["ADMIN"]).status_code == 204
    assert client.get("/api/v1/auth/me", headers=headers["ADMIN"]).status_code == 401


def test_password_change_revokes_token(client, data, headers):
    response = client.post(
        "/api/v1/auth/change-password",
        headers=headers["ADMIN"],
        json={"current_password": "Valid-password-123", "new_password": "New-password-123"},
    )
    assert response.status_code == 204
    assert verify_password("New-password-123", data["users"]["ADMIN"].hashed_password)
    assert client.get("/api/v1/auth/me", headers=headers["ADMIN"]).status_code == 401


def test_persistent_login_lock_and_recovery(client, data, db):
    for _ in range(5):
        assert (
            client.post(
                "/api/v1/auth/login", data={"username": "admin@example.com", "password": "wrong"}
            ).status_code
            == 401
        )
    assert data["users"]["ADMIN"].locked_until > utcnow()
    assert (
        client.post(
            "/api/v1/auth/login",
            data={"username": "admin@example.com", "password": "Valid-password-123"},
        ).status_code
        == 401
    )
    data["users"]["ADMIN"].locked_until = utcnow() - timedelta(seconds=1)
    db.commit()
    assert (
        client.post(
            "/api/v1/auth/login",
            data={"username": "admin@example.com", "password": "Valid-password-123"},
        ).status_code
        == 200
    )


def test_users_and_validation_no_secret_leak(client, data, headers):
    payload = {
        "email": "New@EXAMPLE.com",
        "full_name": "New user",
        "password": "Valid-password-456",
        "role": "ANALYST",
    }
    r = client.post("/api/v1/users", json=payload, headers=headers["ADMIN"])
    assert r.status_code == 201
    assert r.json()["email"] == "new@example.com"
    assert "password" not in r.text
    assert client.post("/api/v1/users", json=payload, headers=headers["ADMIN"]).status_code == 409
    payload["password"] = "secret"
    r = client.post("/api/v1/users", json=payload, headers=headers["ADMIN"])
    assert r.status_code == 422 and "secret" not in r.text
    assert (
        client.patch(
            f"/api/v1/users/{data['users']['ADMIN'].id}",
            json={"is_active": False},
            headers=headers["ADMIN"],
        ).status_code
        == 409
    )
    r = client.patch(
        f"/api/v1/users/{data['users']['ANALYST'].id}",
        json={"is_active": False},
        headers=headers["ADMIN"],
    )
    assert r.status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers["ANALYST"]).status_code == 401
    audit = client.get("/api/v1/audit-logs", headers=headers["ADMIN"])
    assert audit.status_code == 200 and audit.json()["total"] > 0
    assert "Valid-password" not in audit.text and "hashed_password" not in audit.text


def test_password_whitespace_and_bcrypt_bytes(client, headers):
    payload = {
        "email": "spaces@example.com",
        "full_name": "Spaces",
        "password": "  Valid-password-123  ",
    }
    assert client.post("/api/v1/users", json=payload, headers=headers["ADMIN"]).status_code == 201
    assert (
        client.post(
            "/api/v1/auth/login",
            data={"username": payload["email"], "password": payload["password"]},
        ).status_code
        == 200
    )
    payload["email"] = "unicode@example.com"
    payload["password"] = "á" * 40
    r = client.post("/api/v1/users", json=payload, headers=headers["ADMIN"])
    assert r.status_code == 422 and payload["password"] not in r.text
