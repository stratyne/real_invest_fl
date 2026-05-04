# Project Penstock — context/auth.md
# Paste this alongside AGENTS.md when working on auth, users, seeds,
# or Phase 4 access control.
# Last updated: 2026-05-04

## Key Files

real_invest_fl/api/
  main.py                      -- FastAPI app, auth router wired
  deps.py                      -- get_db, get_current_user, require_county_access
  routes/
    auth.py                    -- POST /auth/token, GET /auth/me

real_invest_fl/auth/
  __init__.py
  passwords.py                 -- hash_password, verify_password
  tokens.py                    -- create_access_token, decode_access_token,
                                  extract_user_id

real_invest_fl/db/models/
  user.py                      -- users table
  user_county_access.py        -- user_county_access table
  subscription_bundle.py       -- subscription_bundles + bundle_counties tables
  filter_profile.py            -- user_id added v0.13
  outreach_log.py              -- user_id added v0.13

scripts/seeds/
  seed_superuser.py            -- BLOCKER: must run before Phase 4 auth test
  seed_bundles.py              -- BLOCKER: seeds Pensacola Metro bundle

## Auth Design (locked)

- JWT HS256 via PyJWT
- sub = users.id as string
- email in token payload is display hint only — NEVER used for identity lookup
- Token payload: sub, email, type="access", iat, exp
- Password hashing: bcrypt direct (passlib dropped — incompatible with bcrypt 4.0+)
- get_current_user: decodes JWT → extracts user id → loads User from DB
  raises 401 on failure or inactive user
- require_county_access: superuser bypass → checks user_county_access for
  (user_id, county_fips) row → raises 403 on denial
- Auth routes: POST /auth/token, GET /auth/me ONLY
  Registration, password reset, user management deferred to Phase 4

## Subscription / Access Model (locked)

- County is the fundamental unit of access control and monetization
- Subscription tiers: single county, regional bundle, statewide, enterprise
- First bundle: Pensacola Metro = Escambia (12033) + Santa Rosa (12113)
- User-county authorization: user_county_access join table
- County access enforced via require_county_access dependency — not at
  the application layer
- Multi-user from day one. No single-admin stub acceptable.

## Seed Scripts

### seed_superuser.py (BLOCKER — item 11)
Creates the first superuser account. Must run before any Phase 4 auth
testing can occur. Superuser bypasses all county access checks.

### seed_bundles.py (BLOCKER — item 12)
Seeds the Pensacola Metro subscription bundle:
  - bundle_name: "Pensacola Metro"
  - Counties: Escambia (12033) + Santa Rosa (12113)
  - Activates Santa Rosa county access in the bundle system

## Filter Profile Model (locked)

- Profiles scoped to county_fips
- System profiles: user_id = NULL, visible to all authorized users,
  not editable or deletable by regular users
- Users clone a system profile → "Save as my profile" is first-class UI action
- User profiles: user_id = owner, private, fully editable
- Uniqueness via two partial unique indexes (live in DB since v0.13):
  - System: UNIQUE (county_fips, profile_name) WHERE user_id IS NULL
  - User: UNIQUE (user_id, county_fips, profile_name) WHERE user_id IS NOT NULL
- Cross-county profiles deferred to Phase 3+

## Phase 4 Pre-flight Checklist

Before Phase 4 UI development can begin:
- [ ] Run seed_superuser.py (item 11)
- [ ] Run seed_bundles.py (item 12)
- [ ] Standardize require_county_access path-parameter pattern before
      Phase 4 endpoints proliferate

## Test Status

115 tests passing as of v0.13 completion.
