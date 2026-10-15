"""Cifrado de secretos de integraciones (Fernet / AES-128-CBC + HMAC)."""

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError
from app.models import StoredSecret


def _fernet() -> Fernet:
    key = get_settings().secrets_encryption_key
    if not key:
        raise AppError(
            "Para guardar credenciales de integraciones configurá SECRETS_ENCRYPTION_KEY en el backend "
            "(ver .env.example). No se guardan tokens sin cifrar.",
            code="encryption_not_configured", status_code=422,
        )
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        raise AppError("SECRETS_ENCRYPTION_KEY no es una clave Fernet válida.", code="encryption_invalid",
                       status_code=500)


def store_secret(db: Session, plaintext: str, existing_id: int | None = None) -> int:
    token = _fernet().encrypt(plaintext.encode()).decode()
    if existing_id:
        secret = db.get(StoredSecret, existing_id)
        if secret is not None:
            secret.ciphertext = token
            db.flush()
            return secret.id
    secret = StoredSecret(ciphertext=token)
    db.add(secret)
    db.flush()
    return secret.id


def read_secret(db: Session, secret_id: int | None) -> str | None:
    if not secret_id:
        return None
    secret = db.get(StoredSecret, secret_id)
    if secret is None:
        return None
    try:
        return _fernet().decrypt(secret.ciphertext.encode()).decode()
    except InvalidToken:
        raise AppError("No se pudo descifrar la credencial guardada. Volvé a ingresarla.", code="secret_invalid",
                       status_code=422)
