from __future__ import annotations

import datetime as dt

import jwt

from app import app


def test_auth_me_requires_bearer_token():
    client = app.test_client()
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.get_json()["status"] == "error"


def test_auth_me_returns_subject_from_valid_token():
    app.config["JWT_SECRET_KEY"] = "test-auth-secret"
    token = jwt.encode(
        {
            "sub": "42",
            "username": "student_42",
            "exp": dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5),
        },
        app.config["JWT_SECRET_KEY"],
        algorithm="HS256",
    )
    client = app.test_client()

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.get_json()["user"] == {"id": 42, "username": "student_42"}


def test_register_rejects_invalid_credentials_before_database_access():
    client = app.test_client()
    response = client.post("/api/auth/register", json={"username": "x", "password": "short"})

    assert response.status_code == 400
    assert response.get_json()["status"] == "error"


def test_auth_config_exposes_google_client_id_for_browser(monkeypatch):
    monkeypatch.setitem(app.config, "GOOGLE_CLIENT_ID", "example.apps.googleusercontent.com")
    client = app.test_client()

    response = client.get("/api/auth/config")

    assert response.status_code == 200
    assert response.get_json() == {
        "google_client_id": "example.apps.googleusercontent.com",
        "google_enabled": True,
    }


def test_google_login_returns_first_party_session(monkeypatch):
    monkeypatch.setitem(app.config, "GOOGLE_CLIENT_ID", "example.apps.googleusercontent.com")
    monkeypatch.setitem(app.config, "JWT_SECRET_KEY", "test-auth-secret")
    monkeypatch.setattr(
        "app.login_google_user",
        lambda credential, client_id, secret: {
            "token": "first-party-jwt",
            "user": {"id": 7, "username": "Google Student"},
        },
    )
    client = app.test_client()

    response = client.post("/api/auth/google", json={"credential": "google-id-token"})

    assert response.status_code == 200
    assert response.get_json()["user"]["username"] == "Google Student"


def test_assistant_chat_requires_authentication():
    client = app.test_client()
    response = client.post("/api/assistant/chat", json={"message": "Gợi ý cho mình ngành CNTT"})

    assert response.status_code == 401


def test_assistant_chat_returns_grounded_answer(monkeypatch):
    app.config["JWT_SECRET_KEY"] = "test-auth-secret"
    token = jwt.encode(
        {"sub": "7", "username": "student", "exp": dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5)},
        app.config["JWT_SECRET_KEY"],
        algorithm="HS256",
    )
    monkeypatch.setattr(
        "app.answer_question",
        lambda message, profile, history: {
            "answer": "Bạn có thể cân nhắc các ngành CNTT trong dữ liệu DSS.",
            "sources": [],
            "model": "deepseek-flash",
        },
    )
    client = app.test_client()

    response = client.post(
        "/api/assistant/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "Gợi ý cho mình ngành CNTT", "profile": {}, "history": []},
    )

    assert response.status_code == 200
    assert response.get_json()["answer"].startswith("Bạn có thể")
