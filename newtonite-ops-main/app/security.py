import os
from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

SECRET_KEY = os.getenv("SECRET_KEY", "local-development-only-change-this-secret-before-deploying")
ALGORITHM = "HS256"
_password_hash = PasswordHasher()

def hash_password(password: str) -> str:
    return _password_hash.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    try:
        _password_hash.verify(password_hash, password)
        return True
    except (VerifyMismatchError, VerificationError, ValueError):
        return False

def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user_id), "iat": now, "exp": now + timedelta(hours=8)}, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError, TypeError):
        return None
