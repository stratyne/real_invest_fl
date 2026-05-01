"""
Create the first superuser and grant Escambia County access.

Reads credentials from environment variables — never from hardcoded values.
Safe to run multiple times (ON CONFLICT DO NOTHING on email).

Required environment variables:
    SUPERUSER_EMAIL     — the superuser's login email
    SUPERUSER_PASSWORD  — plaintext password (hashed before storage, never persisted)

These may be set in .env temporarily for initial setup, but must be
removed from .env (and .env must never be committed) immediately after.

Usage:
    SUPERUSER_EMAIL=admin@example.com SUPERUSER_PASSWORD=s3cure python scripts/seeds/seed_superuser.py
    -- or --
    Set both variables in .env, run the script, then remove them from .env.

County grants seeded:
    12033 — Escambia (always granted to superuser)
"""
import sys
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

from sqlalchemy import create_engine, text
from config.settings import settings
from real_invest_fl.auth.passwords import hash_password

ESCAMBIA_FIPS = "12033"


def main() -> None:
    email = os.environ.get("SUPERUSER_EMAIL", "").strip()
    password = os.environ.get("SUPERUSER_PASSWORD", "").strip()

    if not email:
        print("ERROR: SUPERUSER_EMAIL environment variable is not set.")
        sys.exit(1)
    if not password:
        print("ERROR: SUPERUSER_PASSWORD environment variable is not set.")
        sys.exit(1)
    if len(password) < 12:
        print("ERROR: SUPERUSER_PASSWORD must be at least 12 characters.")
        sys.exit(1)

    hashed = hash_password(password)
    # Immediately discard plaintext
    del password

    engine = create_engine(settings.sync_database_url, echo=False)

    with engine.begin() as conn:

        # Insert user
        result = conn.execute(
            text("""
                INSERT INTO users (email, hashed_password, full_name, is_active, is_superuser)
                VALUES (:email, :hashed_password, :full_name, TRUE, TRUE)
                ON CONFLICT (email) DO NOTHING
            """),
            {
                "email":           email,
                "hashed_password": hashed,
                "full_name":       "System Administrator",
            },
        )

        if result.rowcount == 1:
            print(f"Superuser '{email}' created.")
        else:
            print(f"Superuser '{email}' already exists — skipped user insert.")

        # Fetch user id
        row = conn.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": email},
        ).fetchone()
        user_id = row[0]

        # Grant Escambia access (granted_by_user_id NULL = system grant)
        r = conn.execute(
            text("""
                INSERT INTO user_county_access (user_id, county_fips, granted_by_user_id)
                VALUES (:user_id, :county_fips, NULL)
                ON CONFLICT (user_id, county_fips) DO NOTHING
            """),
            {"user_id": user_id, "county_fips": ESCAMBIA_FIPS},
        )
        if r.rowcount == 1:
            print(f"Granted Escambia ({ESCAMBIA_FIPS}) access to '{email}'.")
        else:
            print(f"Escambia access already exists for '{email}' — skipped.")

    print("seed_superuser complete.")


if __name__ == "__main__":
    main()
