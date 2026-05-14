"""
Outreach routes — generate, send, list, skip_trace.

POST /{county_fips}/outreach/generate   — render Jinja2 template, write
                                          listing_scores audit row (scoring
                                          columns NULL, version='PENDING'
                                          until item 19 is live), write
                                          DRAFT outreach_log row. Returns
                                          draft — does not send.
POST /{county_fips}/outreach/send       — send DRAFT via SendGrid, update
                                          status to SENT or FAILED.
GET  /{county_fips}/outreach            — list current user's outreach_log
                                          rows for the county.
POST /{county_fips}/outreach/skip_trace — return cached skip_trace_cache row
                                          if present and not expired. Returns
                                          501 when BATCHDATA_API_KEY not set.

Scoring note (item 19 PENDING):
    listing_scores rows are written at generate time with deal_score=NULL,
    deal_score_version='PENDING', deal_score_components=NULL,
    passed_filters=NULL. Backfilled when deal scoring engine is live.

CAN-SPAM compliance:
    Every outgoing EMAIL includes settings.BUSINESS_ADDRESS as footer.
    Sourced from settings and rendered as {{ business_address }} in the
    Jinja2 EMAIL template. Not optional.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jinja2 import BaseLoader, Environment, TemplateSyntaxError
from pydantic import BaseModel
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from real_invest_fl.api.deps import county_access, get_current_user, get_db
from config.settings import settings
from real_invest_fl.db.models.filter_profile import FilterProfile
from real_invest_fl.db.models.listing_event import ListingEvent
from real_invest_fl.db.models.listing_score import ListingScore
from real_invest_fl.db.models.outreach_log import OutreachLog
from real_invest_fl.db.models.outreach_template import OutreachTemplate
from real_invest_fl.db.models.property import Property
from real_invest_fl.db.models.skip_trace_cache import SkipTraceCache
from real_invest_fl.db.models.user import User

router = APIRouter(prefix="/{county_fips}/outreach", tags=["outreach"])

# ── Jinja2 environment ────────────────────────────────────────────────────────
# BaseLoader — templates are strings from DB rows, not files on disk.
# undefined is default (silent) — missing variables render as empty string,
# which is intentional for optional fields like calendar_link.
_jinja_env = Environment(loader=BaseLoader(), autoescape=False)


# ── Schemas ───────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    parcel_id: str
    listing_event_id: int
    filter_profile_id: int
    template_id: int
    force: bool = False


class SendRequest(BaseModel):
    outreach_log_id: int


class SkipTraceRequest(BaseModel):
    parcel_id: str


class OutreachLogResponse(BaseModel):
    id: int
    county_fips: str
    parcel_id: str
    listing_event_id: int
    filter_profile_id: int | None
    template_id: int
    listing_score_id: int | None
    recipient_name: str | None
    recipient_email: str | None
    recipient_phone: str | None
    recipient_address1: str | None
    recipient_address2: str | None
    recipient_city: str | None
    recipient_state: str | None
    recipient_zip: str | None
    skip_trace_result: dict | None
    message_subject: str | None
    message_body: str | None
    calendar_link: str | None
    template_type: str
    status: str
    sent_at: datetime | None
    send_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GenerateResponse(BaseModel):
    """
    Returned by generate_outreach.

    warning is populated (and draft is None) when an existing
    listing_scores row is found and force=False. The caller must
    re-submit with force=True to proceed past the warning.

    calendar_link_missing is True when current_user.calendar_link is
    NULL and the selected template is the system EMAIL template. The
    draft is still written — the UI must surface the warning to the user.
    """
    draft: OutreachLogResponse | None = None
    warning: str | None = None
    calendar_link_missing: bool = False


class SkipTraceCacheResponse(BaseModel):
    id: int
    county_fips: str
    parcel_id: str
    skip_trace_result: dict
    fetched_at: datetime
    expires_at: datetime
    provider: str

    model_config = {"from_attributes": True}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _render_template(template_str: str, variables: dict) -> str:
    """Render a Jinja2 template string with the supplied variable map.

    Raises HTTPException 422 on template syntax errors so the caller
    receives a meaningful error rather than a 500.
    """
    try:
        tmpl = _jinja_env.from_string(template_str)
        return tmpl.render(**variables)
    except TemplateSyntaxError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Template syntax error: {exc.message}",
        )


def _build_template_variables(
    prop: Property,
    log: OutreachLog,
    current_user: User,
) -> dict:
    """Assemble the full Jinja2 variable map for both EMAIL and LETTER templates.

    All variables documented in DECISIONS.md Outreach Template Seeding section.
    today_date formatted at render time so it reflects the actual send date.
    """
    return {
        # Property physical address
        "property_address": prop.phy_addr1 or "",
        "property_city":    prop.phy_city  or "",
        "property_zip":     prop.phy_zipcd or "",
        # Owner / recipient
        "owner_name":       prop.own_name  or "",
        # Mailing address (snapshotted on log row at generate time)
        "recipient_address1": log.recipient_address1 or "",
        "recipient_address2": log.recipient_address2 or "",
        "recipient_city":     log.recipient_city     or "",
        "recipient_state":    log.recipient_state    or "",
        "recipient_zip":      log.recipient_zip      or "",
        # Sender
        "sender_name":  current_user.full_name or "",
        "sender_email": current_user.email,
        # Booking link — empty string when NULL so Jinja2 {% if %} block
        # in LETTER template evaluates falsy cleanly
        "calendar_link": log.calendar_link or "",
        # CAN-SPAM footer — required for all EMAIL sends
        "business_address": settings.BUSINESS_ADDRESS,
        # Date — LETTER header
        "today_date": datetime.now(tz=timezone.utc).strftime("%B %d, %Y"),
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=GenerateResponse)
async def generate_outreach(
    request: GenerateRequest,
    county_fips: str = Depends(county_access()),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GenerateResponse:
    """Render a Jinja2 template for a property and write a DRAFT outreach_log row.

    Does not send. Returns the draft for user review before send_outreach
    is called. See module docstring for full lifecycle description.
    """
    # ── 1. Validate listing_event ─────────────────────────────────────────────
    le_result = await db.execute(
        select(ListingEvent).where(ListingEvent.id == request.listing_event_id)
    )
    listing_event: ListingEvent | None = le_result.scalar_one_or_none()

    if listing_event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Listing event not found")
    if listing_event.county_fips != county_fips:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Listing event not found in this county")
    if listing_event.parcel_id != request.parcel_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Listing event does not match supplied parcel_id")

    # ── 2. Validate filter_profile ────────────────────────────────────────────
    fp_result = await db.execute(
        select(FilterProfile).where(FilterProfile.id == request.filter_profile_id)
    )
    filter_profile: FilterProfile | None = fp_result.scalar_one_or_none()

    if filter_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Filter profile not found")
    # Visibility: system profile (user_id IS NULL) or owned by current user
    if filter_profile.user_id is not None and filter_profile.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Filter profile not found")

    # ── 3. Validate template ──────────────────────────────────────────────────
    tmpl_result = await db.execute(
        select(OutreachTemplate).where(OutreachTemplate.id == request.template_id)
    )
    template: OutreachTemplate | None = tmpl_result.scalar_one_or_none()

    if template is None or not template.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Template not found or inactive")
    # Visibility: system template (user_id IS NULL) or owned by current user
    if template.user_id is not None and template.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Template not found or inactive")

    # ── 4. Re-generate blocking check ─────────────────────────────────────────
    existing_score_result = await db.execute(
        select(ListingScore).where(
            ListingScore.listing_event_id == request.listing_event_id,
            ListingScore.filter_profile_id == request.filter_profile_id,
        )
    )
    existing_score: ListingScore | None = existing_score_result.scalar_one_or_none()

    if existing_score is not None and not request.force:
        return GenerateResponse(
            warning=(
                "Outreach has already been generated for this listing event and "
                "filter profile. Submit with force=true to generate a new draft."
            )
        )

    # ── 5. Write listing_scores audit row ─────────────────────────────────────
    # deal_score columns are NULL (version='PENDING') until item 19 is live.
    # uq_ls_event_profile prevents duplicate rows — only written on first
    # generate or when force=True (existing row is NOT overwritten on force).
    listing_score: ListingScore | None = existing_score
    if listing_score is None:
        listing_score = ListingScore(
            listing_event_id=request.listing_event_id,
            filter_profile_id=request.filter_profile_id,
            user_id=current_user.id,
            county_fips=county_fips,
            passed_filters=None,
            filter_rejection_reasons=None,
            deal_score=None,
            deal_score_version="PENDING",
            deal_score_components=None,
        )
        db.add(listing_score)
        await db.flush()
        # flush to get listing_score.id before writing outreach_log row

    # ── 6. Resolve property snapshot ──────────────────────────────────────────
    prop_result = await db.execute(
        select(Property).where(
            Property.county_fips == county_fips,
            Property.parcel_id == request.parcel_id,
        )
    )
    prop: Property | None = prop_result.scalar_one_or_none()

    if prop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Property not found")

    # ── 7. Resolve skip_trace_cache snapshot ──────────────────────────────────
    now_utc = datetime.now(tz=timezone.utc)
    stc_result = await db.execute(
        select(SkipTraceCache).where(
            SkipTraceCache.county_fips == county_fips,
            SkipTraceCache.parcel_id == request.parcel_id,
            SkipTraceCache.expires_at > now_utc,
        )
    )
    stc: SkipTraceCache | None = stc_result.scalar_one_or_none()
    skip_trace_snapshot = stc.skip_trace_result if stc is not None else None

    # ── 8. Calendar link warning flag ─────────────────────────────────────────
    # Warn when user has no calendar_link and selected template is system EMAIL.
    # Draft is still written — warning is surfaced in response for UI to display.
    calendar_link_missing = (
        current_user.calendar_link is None
        and template.user_id is None
        and template.template_type == "EMAIL"
    )

    # ── 9. Build DRAFT outreach_log row (pre-render) ──────────────────────────
    log = OutreachLog(
        county_fips=county_fips,
        parcel_id=request.parcel_id,
        user_id=current_user.id,
        listing_event_id=request.listing_event_id,
        filter_profile_id=request.filter_profile_id,
        template_id=request.template_id,
        listing_score_id=listing_score.id,
        # Recipient snapshot from properties
        recipient_name=prop.own_name,
        recipient_email=None,
        # own_email not on properties — populated from skip_trace_cache only
        recipient_phone=None,
        # own_phone not on properties — populated from skip_trace_cache only
        recipient_address1=prop.own_addr1,
        recipient_address2=prop.own_addr2,
        recipient_city=prop.own_city,
        recipient_state=prop.own_state,
        recipient_zip=prop.own_zipcd,
        # Skip-trace snapshot
        skip_trace_result=skip_trace_snapshot,
        # Booking link snapshot
        calendar_link=current_user.calendar_link,
        # Template type snapshot
        template_type=template.template_type,
        status="DRAFT",
        # Message fields populated after render below
        message_subject=None,
        message_body=None,
    )

    # ── 10. Render Jinja2 template ────────────────────────────────────────────
    variables = _build_template_variables(prop, log, current_user)

    if template.subject_template and template.template_type == "EMAIL":
        log.message_subject = _render_template(template.subject_template, variables)

    log.message_body = _render_template(template.body_template, variables)

    # ── 11. Persist and return ────────────────────────────────────────────────
    db.add(log)
    await db.commit()
    await db.refresh(log)

    return GenerateResponse(
        draft=OutreachLogResponse.model_validate(log),
        warning=None,
        calendar_link_missing=calendar_link_missing,
    )


@router.post("/send", response_model=OutreachLogResponse)
async def send_outreach(
    request: SendRequest,
    county_fips: str = Depends(county_access()),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OutreachLogResponse:
    """Send a DRAFT outreach_log row via SendGrid.

    Validates ownership and DRAFT status before sending.
    Updates status to SENT on success, FAILED on error.
    LETTER template_type is rejected — LETTER output is client-side only
    (react-to-print). This route is EMAIL only.
    """
    # ── Validate SendGrid is configured ──────────────────────────────────────
    if not settings.SENDGRID_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email sending is not configured",
        )

    # ── Load and validate log row ─────────────────────────────────────────────
    log_result = await db.execute(
        select(OutreachLog).where(OutreachLog.id == request.outreach_log_id)
    )
    log: OutreachLog | None = log_result.scalar_one_or_none()

    if log is None or log.county_fips != county_fips:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Outreach log entry not found")
    if log.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Not authorised to send this outreach")
    if log.status != "DRAFT":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot send — current status is {log.status}",
        )
    if log.template_type == "LETTER":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="LETTER templates are rendered client-side. Use the print "
                   "function in the UI — this endpoint is EMAIL only.",
        )
    if not log.message_body:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="message_body is empty — regenerate the draft before sending",
        )
    if not log.recipient_email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No recipient email address — run skip trace first",
        )

    # ── Send via SendGrid ─────────────────────────────────────────────────────
    try:
        message = Mail(
            from_email=current_user.email,
            to_emails=log.recipient_email,
            subject=log.message_subject or "(no subject)",
            html_content=log.message_body,
        )
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        sg.send(message)

        log.status = "SENT"
        log.sent_at = datetime.now(tz=timezone.utc)
        log.send_error = None

    except Exception as exc:  # noqa: BLE001
        log.status = "FAILED"
        log.send_error = str(exc)

    await db.commit()
    await db.refresh(log)
    return OutreachLogResponse.model_validate(log)


@router.get("", response_model=list[OutreachLogResponse])
async def list_outreach(
    county_fips: str = Depends(county_access()),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OutreachLogResponse]:
    """Return outreach_log rows for the county scoped to current_user.

    Superusers see only their own rows — superuser privilege is county
    access bypass, not data omniscience. Cross-user visibility belongs
    on a separate admin route if ever needed.
    """
    result = await db.execute(
        select(OutreachLog).where(
            OutreachLog.county_fips == county_fips,
            OutreachLog.user_id == current_user.id,
        ).order_by(OutreachLog.created_at.desc())
    )
    logs = result.scalars().all()
    return [OutreachLogResponse.model_validate(log) for log in logs]


@router.post("/skip_trace", response_model=SkipTraceCacheResponse)
async def skip_trace(
    request: SkipTraceRequest,
    county_fips: str = Depends(county_access()),
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> SkipTraceCacheResponse:
    """Return cached skip_trace_cache row if present and not expired.

    Returns 501 when BATCHDATA_API_KEY is not configured — live
    integration is deferred (item 44). Returns 404 when no non-expired
    cache row exists for the parcel.
    """
    if not settings.BATCHDATA_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Skip trace is not yet configured",
        )

    now_utc = datetime.now(tz=timezone.utc)
    result = await db.execute(
        select(SkipTraceCache).where(
            SkipTraceCache.county_fips == county_fips,
            SkipTraceCache.parcel_id == request.parcel_id,
            SkipTraceCache.expires_at > now_utc,
        )
    )
    cached: SkipTraceCache | None = result.scalar_one_or_none()

    if cached is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No cached skip trace result found for this parcel",
        )

    return SkipTraceCacheResponse.model_validate(cached)
