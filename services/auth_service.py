"""Database-backed account helpers for the public API."""

from __future__ import annotations

import datetime as dt
import hashlib
import re

import jwt
from google.auth.transport import requests as google_requests
from google.auth.exceptions import GoogleAuthError
from google.oauth2 import id_token as google_id_token
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from services.data_repository import get_db_connection

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,50}$")
MIN_PASSWORD_LENGTH = 8
TOKEN_TTL_DAYS = 7


class AuthError(Exception):
    """A safe, client-facing authentication error."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def validate_credentials(username: object, password: object) -> tuple[str, str]:
    normalized_username = str(username or "").strip()
    raw_password = str(password or "")
    if not USERNAME_PATTERN.fullmatch(normalized_username):
        raise AuthError("Tên đăng nhập gồm 3–50 ký tự: chữ cái, số, dấu chấm, gạch nối hoặc gạch dưới.")
    if len(raw_password) < MIN_PASSWORD_LENGTH or len(raw_password) > 128:
        raise AuthError("Mật khẩu phải có từ 8 đến 128 ký tự.")
    return normalized_username, raw_password


def _create_users_table(connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                google_sub VARCHAR(255) UNIQUE,
                display_name VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )
    # Existing deployments may have been created before Google sign-in was added.
    connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS google_sub VARCHAR(255)"))
    connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name VARCHAR(255)"))
    connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS users_google_sub_unique "
            "ON users (google_sub) WHERE google_sub IS NOT NULL"
        )
    )


def _issue_token(user_id: int, username: str, secret_key: str) -> str:
    if not secret_key:
        raise AuthError("Dịch vụ đăng nhập chưa được cấu hình.", 503)
    now = dt.datetime.now(dt.UTC)
    return jwt.encode(
        {"sub": str(user_id), "username": username, "iat": now, "exp": now + dt.timedelta(days=TOKEN_TTL_DAYS)},
        secret_key,
        algorithm="HS256",
    )


def register_user(username: object, password: object, secret_key: str) -> dict:
    username, password = validate_credentials(username, password)
    connection = get_db_connection()
    if connection is None:
        raise AuthError("Dịch vụ tài khoản chưa kết nối được cơ sở dữ liệu.", 503)
    try:
        with connection.begin():
            _create_users_table(connection)
            exists = connection.execute(text("SELECT id FROM users WHERE username = :username"), {"username": username}).fetchone()
            if exists:
                raise AuthError("Tên đăng nhập đã được sử dụng.", 409)
            row = connection.execute(
                text("INSERT INTO users (username, password_hash) VALUES (:username, :password_hash) RETURNING id"),
                {"username": username, "password_hash": generate_password_hash(password)},
            ).fetchone()
        return {"token": _issue_token(int(row[0]), username, secret_key), "user": {"id": int(row[0]), "username": username}}
    except AuthError:
        raise
    except IntegrityError as error:
        if "unique" in str(error).casefold():
            raise AuthError("Tên đăng nhập đã được sử dụng.", 409) from error
        raise AuthError("Không thể tạo tài khoản lúc này.", 503) from error
    except SQLAlchemyError as error:
        raise AuthError("Không thể tạo tài khoản lúc này.", 503) from error
    finally:
        connection.close()


def login_user(username: object, password: object, secret_key: str) -> dict:
    username, password = validate_credentials(username, password)
    connection = get_db_connection()
    if connection is None:
        raise AuthError("Dịch vụ tài khoản chưa kết nối được cơ sở dữ liệu.", 503)
    try:
        with connection.begin():
            _create_users_table(connection)
            user = connection.execute(
                text("SELECT id, username, password_hash FROM users WHERE username = :username"),
                {"username": username},
            ).fetchone()
        if user is None or not check_password_hash(user.password_hash, password):
            raise AuthError("Tên đăng nhập hoặc mật khẩu không đúng.", 401)
        return {"token": _issue_token(int(user.id), str(user.username), secret_key), "user": {"id": int(user.id), "username": str(user.username)}}
    except AuthError:
        raise
    except SQLAlchemyError as error:
        raise AuthError("Không thể đăng nhập lúc này.", 503) from error
    finally:
        connection.close()


def login_google_user(credential: object, client_id: str, secret_key: str) -> dict:
    if not isinstance(credential, str) or not credential.strip():
        raise AuthError("Google chưa trả về thông tin đăng nhập.")
    if not client_id:
        raise AuthError("Đăng nhập Google chưa được cấu hình.", 503)

    try:
        identity = google_id_token.verify_oauth2_token(
            credential.strip(), google_requests.Request(), client_id
        )
    except (ValueError, GoogleAuthError) as error:
        # Verification checks the signature, audience, issuer and expiry before
        # any identity fields are accepted.
        raise AuthError("Không thể xác minh tài khoản Google.", 401) from error

    google_sub = str(identity.get("sub", "")).strip()
    email = str(identity.get("email", "")).strip()
    display_name = str(identity.get("name") or email or "Google user").strip()[:255]
    if not google_sub or not email or not identity.get("email_verified"):
        raise AuthError("Tài khoản Google cần có email đã xác minh.", 401)

    connection = get_db_connection()
    if connection is None:
        raise AuthError("Dịch vụ tài khoản chưa kết nối được cơ sở dữ liệu.", 503)
    try:
        with connection.begin():
            _create_users_table(connection)
            user = connection.execute(
                text("SELECT id, username, display_name FROM users WHERE google_sub = :google_sub"),
                {"google_sub": google_sub},
            ).fetchone()
            if user is None:
                username = f"google_{hashlib.sha256(google_sub.encode()).hexdigest()[:16]}"
                user = connection.execute(
                    text(
                        "INSERT INTO users (username, password_hash, google_sub, display_name) "
                        "VALUES (:username, :password_hash, :google_sub, :display_name) "
                        "RETURNING id, username, display_name"
                    ),
                    {
                        "username": username,
                        "password_hash": generate_password_hash(hashlib.sha256(google_sub.encode()).hexdigest()),
                        "google_sub": google_sub,
                        "display_name": display_name,
                    },
                ).fetchone()
        account_name = str(user.display_name or user.username)
        return {
            "token": _issue_token(int(user.id), account_name, secret_key),
            "user": {"id": int(user.id), "username": account_name},
        }
    except AuthError:
        raise
    except (IntegrityError, SQLAlchemyError) as error:
        raise AuthError("Không thể đăng nhập Google lúc này.", 503) from error
    finally:
        connection.close()


def decode_token(token: str, secret_key: str) -> dict:
    if not secret_key:
        raise AuthError("Dịch vụ đăng nhập chưa được cấu hình.", 503)
    try:
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        return {"id": int(payload["sub"]), "username": str(payload["username"])}
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, KeyError, TypeError, ValueError) as error:
        raise AuthError("Phiên đăng nhập không hợp lệ hoặc đã hết hạn.", 401) from error
