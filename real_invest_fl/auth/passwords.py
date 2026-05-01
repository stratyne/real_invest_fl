"""Password hashing utilities using bcrypt directly.

passlib 1.7.x is incompatible with bcrypt 4.0+ (raises ValueError on
any hash/verify call). We call bcrypt directly instead — it has a
stable, minimal API that does not require a wrapper library.

bcrypt silently truncates passwords longer than 72 bytes, which is
standard and correct bcrypt behaviour.
"""
import bcrypt


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of plain-text password as a UTF-8 string."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches hashed. False on any mismatch."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False
