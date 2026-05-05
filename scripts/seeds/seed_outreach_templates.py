"""
Seed system outreach templates.

Inserts two system-owned templates (user_id IS NULL):
    - System Default Email  (EMAIL)
    - System Default Letter (LETTER)

Idempotent — safe to run multiple times.
ON CONFLICT (template_name) WHERE user_id IS NULL DO NOTHING
uq_ot_system_name partial unique index.

Usage:
    python scripts/seeds/seed_outreach_templates.py
"""
import sys
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)

from sqlalchemy import create_engine, text
from config.settings import settings


# --------------------------------------------------------------------------- #
# Template definitions                                                          #
# --------------------------------------------------------------------------- #

EMAIL_SUBJECT = "Your property at {{ property_address }} — quick question"

EMAIL_BODY = """\
Hi {{ owner_name }},

My name is {{ sender_name }}, and I'm a private real estate investor
in the {{ property_city }} area. I came across your property at
{{ property_address }}, {{ property_city }}, FL {{ property_zip }}
and wanted to reach out directly.

I'm not here with a hard pitch — I'd simply like to learn a bit more
about your situation and find out whether selling might be something
you'd consider, either now or down the road.

If you're open to a brief, no-obligation conversation, I'd be happy
to work around your schedule. You can book a time that suits you here:

{{ calendar_link }}

Or feel free to reply directly to this email at {{ sender_email }} and
we can go from there.

Either way, no pressure at all. I appreciate you taking a moment to
read this.

Warm regards,
{{ sender_name }}
{{ sender_email }}

--
{{ business_address }}\
"""

LETTER_BODY = """\
{{ today_date }}


{{ owner_name }}
{{ recipient_address1 }}{% if recipient_address2 %}
{{ recipient_address2 }}{% endif %}
{{ recipient_city }}, {{ recipient_state }} {{ recipient_zip }}


Re: Your property at {{ property_address }}, {{ property_city }}, FL {{ property_zip }}

Dear {{ owner_name }},

My name is {{ sender_name }}, and I am a private real estate investor
based in the {{ property_city }} area. I am writing to you directly
because I have an interest in properties in your neighborhood and
wanted to introduce myself.

I am not writing to pressure you into anything. I would simply like
to start a conversation to learn more about your situation and
find out whether selling your property might be something you would
consider, now or in the future.

If you are open to a brief, no-obligation conversation, I would
welcome the opportunity to connect.{% if calendar_link %} You are
welcome to schedule a time at your convenience here:

{{ calendar_link }}
{% endif %}
You may also reach me directly by email at {{ sender_email }}.

Thank you for your time and consideration.

Sincerely,


{{ sender_name }}
{{ sender_email }}\
"""

TEMPLATES = [
    {
        "template_name":    "System Default Email",
        "description":      (
            "System-owned email template for initial outreach. "
            "Private investor tone. Opens dialog — no hard pitch. "
            "Requires users.calendar_link for best results."
        ),
        "template_type":    "EMAIL",
        "subject_template": EMAIL_SUBJECT,
        "body_template":    EMAIL_BODY,
        "county_fips":      None,   # global — available across all counties
        "is_active":        True,
    },
    {
        "template_name":    "System Default Letter",
        "description":      (
            "System-owned letter template for initial outreach. "
            "Formal full-block format. Private investor tone. "
            "Opens dialog — no hard pitch. "
            "Printed and mailed to owner mailing address."
        ),
        "template_type":    "LETTER",
        "subject_template": None,   # LETTER has no subject line
        "body_template":    LETTER_BODY,
        "county_fips":      None,   # global — available across all counties
        "is_active":        True,
    },
]


# --------------------------------------------------------------------------- #
# Seed                                                                          #
# --------------------------------------------------------------------------- #

def main() -> None:
    engine = create_engine(settings.sync_database_url, echo=False)

    with engine.begin() as conn:
        for tmpl in TEMPLATES:
            result = conn.execute(
                text("""
                    INSERT INTO outreach_templates (
                        user_id,
                        county_fips,
                        template_name,
                        description,
                        template_type,
                        subject_template,
                        body_template,
                        is_active
                    )
                    VALUES (
                        NULL,
                        :county_fips,
                        :template_name,
                        :description,
                        :template_type,
                        :subject_template,
                        :body_template,
                        :is_active
                    )
                    ON CONFLICT (template_name) WHERE user_id IS NULL DO NOTHING
                """),
                {
                    "county_fips":      tmpl["county_fips"],
                    "template_name":    tmpl["template_name"],
                    "description":      tmpl["description"],
                    "template_type":    tmpl["template_type"],
                    "subject_template": tmpl["subject_template"],
                    "body_template":    tmpl["body_template"],
                    "is_active":        tmpl["is_active"],
                },
            )
            if result.rowcount == 1:
                print(f"Inserted template '{tmpl['template_name']}'.")
            else:
                print(
                    f"Template '{tmpl['template_name']}' already exists — skipped."
                )

    print("seed_outreach_templates complete.")


if __name__ == "__main__":
    main()
