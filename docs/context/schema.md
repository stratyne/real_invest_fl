# Project Penstock — context/schema.md
# Complete current schema reference. Paste alongside AGENTS.md when
# schema questions arise or when writing migrations, ORM models,
# or query-time logic.
# Always current — updated after every migration.
# Last updated: 2026-05-28

---

## ROOT Path Bootstrap Rules

| File location | ROOT expression |
|---|---|
| scripts/*.py | Path(__file__).resolve().parent.parent |
| real_invest_fl/ingest/*.py | Path(__file__).resolve().parent.parent.parent |
| real_invest_fl/scrapers/*.py | Path(__file__).resolve().parent.parent.parent |
| real_invest_fl/ingest/staging_parsers/*.py | Path(__file__).resolve().parent.parent.parent.parent |

Standard bootstrap block:

    ROOT = Path(__file__).resolve().parent.parent.parent  # adjust per table
    sys.path.insert(0, str(ROOT))
    from config.settings import settings
    from sqlalchemy import create_engine, text
    engine = create_engine(settings.sync_database_url)

---

## Migration Chain

HEAD = o6p7q8r9s0t1 (v0.22) — live and verified

| Rev | Version | Description |
|---|---|---|
| 54c4159dbf59 | v0.2 | initial schema — 14 tables |
| 4ca6031e21c4 | v0.3 | NAL rename |
| f422169456bd | v0.4 | replace scalar with JSON filter |
| 5381f80387ed | v0.5 | zoning, nav_total_assessment, alt_key index |
| 390bc7eab733 | v0.6 | ingest_runs full implementation |
| 25a1f5163f3b | v0.7 | county_zips foreign key |
| a1b2c3d4e5f6 | v0.8 | widen own_state VARCHAR(2) → VARCHAR(25) |
| b2c3d4e5f6a7 | v0.9 | add jv_per_sqft, arv_estimate, arv_spread, list_price |
| c3d4e5f6a7b8 | v0.10 | add signal_tier, signal_type to listing_events |
| d4e5f6a7b8c9 | v0.11 | add bed_bath_source to properties |
| e5f6a7b8c9d0 | v0.12 | add data_source_status table |
| f7a8b9c0d1e2 | v0.13 | user/tenant model |
| g8h9i0j1k2l3 | v0.14 | add parcel_sale_history table |
| h9i0j1k2l3m4 | v0.15 | parcel_sale_history grantor/grantee NOT NULL DEFAULT '' |
| i0j1k2l3m4n5 | v0.16 | listing_scores table; strip scoring columns from listing_events |
| j1k2l3m4n5o6 | v0.17 | Phase 4 outreach schema |
| k2l3m4n5o6p7 | v0.18 | user_profile_prefs |
| l3m4n5o6p7q8 | v0.19 | multi-county filter profiles — county_fips VARCHAR(5)[] |
| m4n5o6p7q8r9 | v0.20 | listing_events workflow_status CHECK constraint |
| n5o6p7q8r9s0 | v0.21 | add arv_source to properties |
| o6p7q8r9s0t1 | v0.22 | add sales_history_enriched_at to properties |

---

## Table Schemas

### properties

    county_fips               VARCHAR(5)     NOT NULL
    parcel_id                 VARCHAR(30)    NOT NULL
    state_par_id              VARCHAR(30)    NOT NULL
    co_no                     INTEGER
    asmnt_yr                  INTEGER
    dor_uc                    VARCHAR(10)
    pa_uc                     VARCHAR(10)
    jv                        INTEGER
    av_nsd                    INTEGER
    tv_nsd                    INTEGER
    const_class               INTEGER
    eff_yr_blt                INTEGER
    act_yr_blt                INTEGER
    tot_lvg_area              INTEGER
    lnd_sqfoot                INTEGER
    no_buldng                 INTEGER
    no_res_unts               INTEGER
    own_name                  VARCHAR(200)
    own_addr1                 VARCHAR(200)
    own_addr2                 VARCHAR(200)
    own_city                  VARCHAR(100)
    own_state                 VARCHAR(25)
    own_zipcd                 VARCHAR(10)
    phy_addr1                 VARCHAR(300)
    phy_city                  VARCHAR(100)
    phy_zipcd                 VARCHAR(10)
    absentee_owner            BOOLEAN
    foundation_type           VARCHAR(100)
    exterior_wall             VARCHAR(100)
    roof_type                 VARCHAR(100)
    bedrooms                  INTEGER
    bathrooms                 NUMERIC(4,1)
    cama_quality_code         VARCHAR(10)
    cama_condition_code       VARCHAR(10)
    cama_enriched_at          TIMESTAMPTZ
	sales_history_enriched_at TIMESTAMPTZ
    geom                      geometry(Point,4326)
    latitude                  NUMERIC(10,7)
    longitude                 NUMERIC(10,7)
    mqi_qualified             BOOLEAN        NOT NULL   -- POC artifact; always false
    mqi_qualified_at          TIMESTAMPTZ               -- POC artifact; pending removal
    mqi_rejection_reasons     JSONB                     -- POC artifact; pending removal
    mqi_stage                 VARCHAR(10)
    seller_probability_score  NUMERIC(5,4)
    seller_score_updated_at   TIMESTAMPTZ
    permit_count              INTEGER
    estimated_rehab_per_sqft  NUMERIC(6,2)
    raw_nal_json              JSONB
    raw_cama_json             JSONB
    nal_ingested_at           TIMESTAMPTZ
    created_at                TIMESTAMPTZ    NOT NULL   DEFAULT now()
    updated_at                TIMESTAMPTZ    NOT NULL   DEFAULT now()
    imp_qual                  INTEGER
    spec_feat_val             INTEGER
    av_sd                     INTEGER
    tv_sd                     INTEGER
    jv_hmstd                  INTEGER
    lnd_val                   INTEGER
    exmpt_01                  INTEGER
    multi_par_sal1            VARCHAR(1)
    qual_cd1                  VARCHAR(2)
    vi_cd1                    VARCHAR(1)
    sale_prc1                 INTEGER
    sale_yr1                  INTEGER
    sale_mo1                  INTEGER
    sal_chng_cd1              VARCHAR(1)
    multi_par_sal2            VARCHAR(1)
    qual_cd2                  VARCHAR(2)
    vi_cd2                    VARCHAR(1)
    sale_prc2                 INTEGER
    sale_yr2                  INTEGER
    sale_mo2                  INTEGER
    sal_chng_cd2              VARCHAR(1)
    own_state_dom             VARCHAR(2)
    distr_cd                  INTEGER
    distr_yr                  INTEGER
    nconst_val                INTEGER
    del_val                   INTEGER
    par_splt                  VARCHAR(5)
    spass_cd                  VARCHAR(1)
    mkt_ar                    VARCHAR(3)
    nbrhd_cd                  VARCHAR(10)
    census_bk                 VARCHAR(16)
    twn                       VARCHAR(3)
    rng                       VARCHAR(3)
    sec                       VARCHAR(3)
    dt_last_inspt             VARCHAR(4)
    alt_key                   VARCHAR(26)
    s_legal                   VARCHAR(30)
    improvement_to_land_ratio NUMERIC(8,4)
    soh_compression_ratio     NUMERIC(6,4)
    years_since_last_sale     INTEGER
    zoning                    VARCHAR(20)
    nav_total_assessment      NUMERIC(12,2)
    jv_per_sqft               NUMERIC
    arv_estimate              INTEGER
    arv_source                VARCHAR(20)    -- COMP | JV_FALLBACK | ZESTIMATE | MANUAL
    arv_spread                INTEGER
    list_price                INTEGER
    bed_bath_source           VARCHAR(50)

    PRIMARY KEY (county_fips, parcel_id)  -- uq_county_parcel

    Indexes:
      idx_properties_geom         gist (geom)
      ix_properties_act_yr_blt    btree (act_yr_blt)
      ix_properties_alt_key       btree (alt_key)
      ix_properties_census_bk     btree (census_bk)
      ix_properties_const_class   btree (const_class)
      ix_properties_county_fips   btree (county_fips)
      ix_properties_dor_uc        btree (dor_uc)
      ix_properties_jv            btree (jv)
      ix_properties_mkt_ar        btree (mkt_ar)
      ix_properties_mqi_qualified btree (mqi_qualified)
      ix_properties_phy_zipcd     btree (phy_zipcd)
      ix_properties_sale_yr1      btree (sale_yr1)
      ix_properties_state_par_id  btree (state_par_id)

### listing_events

    id                        INTEGER        PK autoincrement
    county_fips               VARCHAR(5)     NOT NULL
    parcel_id                 VARCHAR(30)    NOT NULL
    listing_type              VARCHAR(50)
    list_price                INTEGER
    list_date                 DATE
    expiry_date               DATE
    days_on_market            INTEGER
    source                    VARCHAR(100)
    listing_url               VARCHAR(1000)
    listing_agent_name        VARCHAR(200)
    listing_agent_email       VARCHAR(200)
    listing_agent_phone       VARCHAR(30)
    mls_number                VARCHAR(50)
    price_per_sqft            NUMERIC(8,2)
    arv_estimate              INTEGER
    arv_source                VARCHAR(20)
    rehab_cost_estimate       INTEGER
    arv_spread                INTEGER
    zestimate_value           INTEGER
    zestimate_discount_pct    NUMERIC(6,3)
    zestimate_fetched_at      TIMESTAMPTZ
    workflow_status           VARCHAR(30)    NOT NULL
                                             -- CHECK constraint (v0.20):
                                             -- workflow_status IN ('NEW','REVIEWED',
                                             --   'APPROVE_SEND','SENT','RESPONDED',
                                             --   'REJECTED','CLOSED')
    notes                     TEXT
    raw_listing_json          JSONB
    scraped_at                TIMESTAMPTZ
    created_at                TIMESTAMPTZ    NOT NULL   DEFAULT now()
    updated_at                TIMESTAMPTZ    NOT NULL   DEFAULT now()
    signal_tier               INTEGER
    signal_type               VARCHAR(50)

    Indexes:
      listing_events_pkey   PRIMARY KEY (id)
      ix_le_county_parcel   btree (county_fips, parcel_id)
      ix_le_listing_type    btree (listing_type)
      ix_le_status          btree (workflow_status)
      ix_le_signal_tier     btree (signal_tier)
      ix_le_signal_type     btree (signal_type)

### listing_scores

    id                        INTEGER        PK autoincrement
    listing_event_id          INTEGER        NOT NULL  FK → listing_events.id ON DELETE CASCADE
    filter_profile_id         INTEGER        NOT NULL  FK → filter_profiles.id ON DELETE CASCADE
    user_id                   INTEGER        NOT NULL  FK → users.id ON DELETE CASCADE
    county_fips               VARCHAR(5)     NOT NULL
    passed_filters            BOOLEAN
    filter_rejection_reasons  JSONB
    deal_score                NUMERIC(5,4)
    deal_score_version        VARCHAR(20)
    deal_score_components     JSONB
    scored_at                 TIMESTAMPTZ    NOT NULL   DEFAULT now()

    UNIQUE (listing_event_id, filter_profile_id)  -- uq_ls_event_profile

    Indexes:
      listing_scores_pkey        PRIMARY KEY (id)
      ix_ls_user_profile         btree (user_id, filter_profile_id)
      ix_ls_user_county_score    btree (user_id, county_fips, deal_score)
      ix_ls_passed_filters       btree (filter_profile_id, passed_filters)

### users

    id               INTEGER        PK autoincrement
    email            VARCHAR(255)   NOT NULL UNIQUE
    hashed_password  VARCHAR(255)   NOT NULL
    full_name        VARCHAR(200)
    is_active        BOOLEAN        NOT NULL   DEFAULT true
    is_superuser     BOOLEAN        NOT NULL   DEFAULT false
    calendar_link    VARCHAR(1000)
    created_at       TIMESTAMPTZ    NOT NULL   DEFAULT now()
    updated_at       TIMESTAMPTZ    NOT NULL   DEFAULT now()

### user_county_access

    id                  INTEGER      PK autoincrement
    user_id             INTEGER      NOT NULL  FK → users.id ON DELETE CASCADE
    county_fips         VARCHAR(5)   NOT NULL  FK → counties.county_fips
    granted_at          TIMESTAMPTZ  NOT NULL  DEFAULT now()
    granted_by_user_id  INTEGER               FK → users.id ON DELETE SET NULL

    UNIQUE (user_id, county_fips)

### subscription_bundles

    id           INTEGER       PK autoincrement
    bundle_name  VARCHAR(100)  NOT NULL UNIQUE
    description  VARCHAR(500)
    is_active    BOOLEAN       NOT NULL  DEFAULT true
    created_at   TIMESTAMPTZ   NOT NULL  DEFAULT now()

### bundle_counties

    bundle_id    INTEGER     NOT NULL  FK → subscription_bundles.id ON DELETE CASCADE
    county_fips  VARCHAR(5)  NOT NULL  FK → counties.county_fips

    PRIMARY KEY (bundle_id, county_fips)

### filter_profiles

    id                        INTEGER       PK autoincrement
    user_id                   INTEGER                 FK → users.id ON DELETE CASCADE
                                                      -- NULL = system profile
    county_fips               VARCHAR(5)[]  NOT NULL  -- array, GIN indexed
    profile_name              VARCHAR(100)  NOT NULL
    description               TEXT
    is_active                 BOOLEAN       NOT NULL  DEFAULT true
    version                   INTEGER       NOT NULL  DEFAULT 1
    filter_criteria           JSONB         NOT NULL
    rehab_cost_per_sqft       FLOAT         NOT NULL  DEFAULT 22.00
    min_comp_sales_for_arv    INTEGER       NOT NULL  DEFAULT 3
    comp_radius_miles         FLOAT         NOT NULL  DEFAULT 1.0
    comp_year_built_tolerance INTEGER       NOT NULL  DEFAULT 15
    listing_type_priority     JSONB         NOT NULL
    deal_score_weights        JSONB         NOT NULL
    allow_automated_outreach  BOOLEAN       NOT NULL  DEFAULT false
    max_outreach_attempts     INTEGER       NOT NULL  DEFAULT 3
    created_at                TIMESTAMPTZ   NOT NULL  DEFAULT now()
    updated_at                TIMESTAMPTZ   NOT NULL  DEFAULT now()

    Partial unique indexes:
    UNIQUE (profile_name) WHERE user_id IS NULL -- uq_fp_system_name
    UNIQUE (user_id, profile_name) WHERE user_id IS NOT NULL -- uq_fp_user_name

    Indexes:
      ix_fp_county_fips_gin  gin (county_fips)

### user_profile_prefs  -- v0.18

    id                  INTEGER      PK autoincrement
    user_id             INTEGER      NOT NULL  FK → users.id ON DELETE CASCADE
    profile_id          INTEGER      NOT NULL  FK → filter_profiles.id ON DELETE CASCADE
    is_favorite         BOOLEAN      NOT NULL  DEFAULT false
    last_searched_at    TIMESTAMPTZ
    last_result_count   INTEGER
    run_count           INTEGER      NOT NULL  DEFAULT 0
    created_at          TIMESTAMPTZ  NOT NULL  DEFAULT now()
    updated_at          TIMESTAMPTZ  NOT NULL  DEFAULT now()

    UNIQUE (user_id, profile_id)  -- uq_upp_user_profile

    Indexes:
      user_profile_prefs_pkey    PRIMARY KEY (id)
      uq_upp_user_profile        UNIQUE (user_id, profile_id)
      ix_upp_user_favorite       btree (user_id, is_favorite)
      ix_upp_user_last_searched  btree (user_id, last_searched_at DESC)

### parcel_sale_history

    id                  INTEGER        PK autoincrement
    county_fips         VARCHAR(5)     NOT NULL
    parcel_id           VARCHAR(30)    NOT NULL
    sale_date           DATE
    sale_price          INTEGER
    instrument_type     VARCHAR(10)    -- WD / QD / CT / TD etc. NULL for current counties
    qualification_code  VARCHAR(5)     -- Q / U / C / V
    sale_type           VARCHAR(5)     -- I / V (Santa Rosa only)
    multi_parcel        BOOLEAN        NOT NULL  DEFAULT false
    grantor             VARCHAR(300)   NOT NULL  DEFAULT ''
    grantee             VARCHAR(300)   NOT NULL  DEFAULT ''
    price_per_sqft      NUMERIC(8,2)
    source              VARCHAR(100)   NOT NULL
    scraped_at          TIMESTAMPTZ    NOT NULL  DEFAULT now()

    UNIQUE (county_fips, parcel_id, sale_date, grantor, grantee)
      -- uq_psh_county_parcel_sale

    Indexes:
      pk_parcel_sale_history   PRIMARY KEY (id)
      ix_psh_county_parcel     btree (county_fips, parcel_id)
      ix_psh_grantee           btree (grantee)
      ix_psh_grantor           btree (grantor)
      ix_psh_qualification_code btree (qualification_code)
      ix_psh_sale_date         btree (sale_date)

### data_source_status

    source               VARCHAR(100)  NOT NULL
    county_fips          VARCHAR(5)    NOT NULL
    display_name         VARCHAR(200)  NOT NULL
    last_success_at      TIMESTAMPTZ
    last_run_at          TIMESTAMPTZ
    last_run_status      VARCHAR(20)             -- SUCCESS | FAILED | PARTIAL
    last_record_count    INTEGER
    last_error_message   TEXT
    created_at           TIMESTAMPTZ   NOT NULL  DEFAULT now()
    updated_at           TIMESTAMPTZ   NOT NULL  DEFAULT now()

    PRIMARY KEY (source, county_fips)

### outreach_templates

    id               INTEGER       PK autoincrement
    user_id          INTEGER                FK → users.id ON DELETE SET NULL
                                            -- NULL = system template
    county_fips      VARCHAR(5)             -- NULL = global template
    template_name    VARCHAR(100)  NOT NULL
    description      TEXT
    template_type    VARCHAR(50)   NOT NULL  -- CHECK: EMAIL | LETTER
    subject_template TEXT                   -- EMAIL only
    body_template    TEXT          NOT NULL
    is_active        BOOLEAN       NOT NULL  DEFAULT true
    created_at       TIMESTAMPTZ   NOT NULL  DEFAULT now()
    updated_at       TIMESTAMPTZ   NOT NULL  DEFAULT now()

    Partial unique indexes:
      UNIQUE (template_name) WHERE user_id IS NULL
        -- uq_ot_system_name
      UNIQUE (user_id, template_name) WHERE user_id IS NOT NULL
        -- uq_ot_user_name

    Indexes:
      ix_ot_user_id        btree (user_id)
      ix_ot_template_type  btree (template_type)

    Check constraints:
      chk_ot_template_type  template_type IN ('EMAIL', 'LETTER')

### skip_trace_cache

    id                  INTEGER       PK autoincrement
    county_fips         VARCHAR(5)    NOT NULL
    parcel_id           VARCHAR(30)   NOT NULL
    skip_trace_result   JSONB         NOT NULL
    fetched_at          TIMESTAMPTZ   NOT NULL  DEFAULT now()
    expires_at          TIMESTAMPTZ   NOT NULL
    provider            VARCHAR(50)   NOT NULL  DEFAULT 'BATCHDATA'
    created_at          TIMESTAMPTZ   NOT NULL  DEFAULT now()

    UNIQUE (county_fips, parcel_id)  -- uq_stc_county_parcel

    Indexes:
      ix_stc_expires_at  btree (expires_at)

### outreach_log

    id                  INTEGER        PK autoincrement
    county_fips         VARCHAR(5)     NOT NULL
    user_id             INTEGER                  FK → users.id ON DELETE CASCADE
    parcel_id           VARCHAR(30)    NOT NULL
    listing_event_id    INTEGER        NOT NULL  FK → listing_events.id ON DELETE CASCADE
    filter_profile_id   INTEGER                  FK → filter_profiles.id ON DELETE SET NULL
    template_id         INTEGER        NOT NULL  FK → outreach_templates.id ON DELETE RESTRICT
    listing_score_id    INTEGER                  FK → listing_scores.id ON DELETE SET NULL
    recipient_name      VARCHAR(200)
    recipient_email     VARCHAR(255)
    recipient_phone     VARCHAR(30)
    recipient_address1  VARCHAR(200)
    recipient_address2  VARCHAR(200)
    recipient_city      VARCHAR(100)
    recipient_state     VARCHAR(25)
    recipient_zip       VARCHAR(10)
    skip_trace_result   JSONB
    message_subject     VARCHAR(500)
    message_body        TEXT
    calendar_link       VARCHAR(1000)
    template_type       VARCHAR(50)    NOT NULL  -- CHECK: EMAIL | LETTER (snapshot)
    status              VARCHAR(30)    NOT NULL  DEFAULT 'DRAFT'
                                                 -- CHECK: DRAFT | SENT | FAILED
    sent_at             TIMESTAMPTZ
    send_error          TEXT
    created_at          TIMESTAMPTZ    NOT NULL  DEFAULT now()
    updated_at          TIMESTAMPTZ    NOT NULL  DEFAULT now()

    Indexes:
      outreach_log_pkey    PRIMARY KEY (id)
      ix_ol_county_user    btree (county_fips, user_id)
      ix_ol_listing_event  btree (listing_event_id)
      ix_ol_status         btree (status)
      ix_ol_parcel         btree (county_fips, parcel_id)

    Check constraints:
      chk_ol_template_type  template_type IN ('EMAIL', 'LETTER')
      chk_ol_status         status IN ('DRAFT', 'SENT', 'FAILED')
