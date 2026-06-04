"""
Create the demo superuser account and grant Escambia + Santa Rosa access.

Reads credentials from environment variables - never from hardcoded values.
Safe to run multiple times (ON CONFLICT DO NOTHING on email).
calendar_link is NOT updated on conflict - remove the account and re-run
if the link needs to change.

Required environment variables:
    DEMO_EMAIL          - the demo account's login email
    DEMO_PASSWORD       - plaintext password (hashed before storage, never persisted)

Optional environment variables:
    DEMO_CALENDAR_LINK  - Google Calendar Appointment Schedule URL (or any booking link).
                          Stored as users.calendar_link. NULL if not set.

These may be set in .env temporarily for initial setup, but must be
removed from .env (and .env must never be committed) immediately after.

Usage:
    DEMO_EMAIL=demo@example.com DEMO_PASSWORD=s3curepassword python scripts/seeds/seed_demo_account.py
    -- or --
    Set variables in .env, run the script, then remove them from .env.

County grants seeded:
    12033 - Escambia
    12113 - Santa Rosa
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

COUNTY_GRANTS = [
    ("12033", "Escambia"),
    ("12113", "Santa Rosa"),
]


def main() -> None:
    email = os.environ.get("DEMO_EMAIL", "").strip()
    password = os.environ.get("DEMO_PASSWORD", "").strip()
    calendar_link = os.environ.get("DEMO_CALENDAR_LINK", "").strip() or None

    if not email:
        print("ERROR: DEMO_EMAIL environment variable is not set.")
        sys.exit(1)
    if not password:
        print("ERROR: DEMO_PASSWORD environment variable is not set.")
        sys.exit(1)
    if len(password) < 12:
        print("ERROR: DEMO_PASSWORD must be at least 12 characters.")
        sys.exit(1)

    hashed = hash_password(password)
    # Immediately discard plaintext
    del password

    engine = create_engine(settings.sync_database_url, echo=False)

    with engine.begin() as conn:

        # ── Insert demo user ─────────────────────────────────────────────
        result = conn.execute(
            text("""
                INSERT INTO users (
                    email,
                    hashed_password,
                    full_name,
                    is_active,
                    is_superuser,
                    calendar_link
                )
                VALUES (
                    :email,
                    :hashed_password,
                    :full_name,
                    TRUE,
                    TRUE,
                    :calendar_link
                )
                ON CONFLICT (email) DO NOTHING
            """),
            {
                "email":           email,
                "hashed_password": hashed,
                "full_name":       "Demo Account",
                "calendar_link":   calendar_link,
            },
        )

        if result.rowcount == 1:
            print(f"Demo account '{email}' created.")
            if calendar_link:
                print(f"calendar_link set.")
            else:
                print("WARNING: DEMO_CALENDAR_LINK not set - calendar_link stored as NULL.")
                print("         Outreach emails will render a blank booking link line.")
                print("         Set DEMO_CALENDAR_LINK and re-seed to fix.")
        else:
            print(f"Demo account '{email}' already exists - skipped user insert.")
            print("NOTE: calendar_link was NOT updated. Remove the account and")
            print("      re-run this script if the calendar link needs to change.")

        # ── Fetch user id ────────────────────────────────────────────────
        row = conn.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": email},
        ).fetchone()
        user_id = row[0]

        # ── Grant county access ──────────────────────────────────────────
        for fips, name in COUNTY_GRANTS:
            r = conn.execute(
                text("""
                    INSERT INTO user_county_access (user_id, county_fips, granted_by_user_id)
                    VALUES (:user_id, :county_fips, NULL)
                    ON CONFLICT (user_id, county_fips) DO NOTHING
                """),
                {"user_id": user_id, "county_fips": fips},
            )
            if r.rowcount == 1:
                print(f"Granted {name} ({fips}) access to '{email}'.")
            else:
                print(f"{name} ({fips}) access already exists for '{email}' - skipped.")

    print("seed_demo_account complete.")


if __name__ == "__main__":
    main()
