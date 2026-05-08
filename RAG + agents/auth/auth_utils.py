# auth_utils.py
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
from jose import jwt, JWTError
from passlib.context import CryptContext
from passlib.exc import UnknownHashError
from dotenv import load_dotenv

load_dotenv()

# New passwords (signup) use Argon2. Legacy / admin seeds often store bcrypt ($2a/$2b/$2y).
# Bcrypt is verified via the `bcrypt` package — passlib's bcrypt backend breaks on bcrypt>=4.
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

JWT_SECRET = os.getenv("JWT_SECRET", "dev_secret_change_me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "43200"))

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, password_hash: str | None) -> bool:
    if not password_hash or not str(password_hash).strip():
        return False
    stored = str(password_hash).strip()
    if stored.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"),
                stored.encode("utf-8"),
            )
        except (ValueError, TypeError):
            return False
    try:
        return pwd_context.verify(plain_password, stored)
    except UnknownHashError:
        return False

def create_access_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload: Dict[str, Any] = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None