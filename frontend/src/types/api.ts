// ── Auth ─────────────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface UserProfile {
  id: number
  email: string
  full_name: string | null
  is_active: boolean
  is_superuser: boolean
  calendar_link: string | null
  created_at: string
}

export interface UserUpdate {
  full_name?: string | null
  calendar_link?: string | null
  password?: string | null
}

// ── Counties ─────────────────────────────────────────────────────────────

export interface CountyResponse {
  county_fips: string
  county_name: string
  state_abbr: string
  dor_county_no: number
  poc_county: boolean
  nal_last_ingested_at: string | null
  cama_last_ingested_at: string | null
}

// ── Dashboard ────────────────────────────────────────────────────────────

export interface ProfileActivityEntry {
  profile_id: number
  profile_name: string
  county_fips: string[]
  is_system: boolean
  is_favorite: boolean
  last_searched_at: string | null
  last_result_count: number | null
  run_count: number
}

export interface OutreachPipelineStatus {
  drafts_pending: number
  sent_this_week: number
  responses_received: number
}

export interface DashboardResponse {
  profile_activity: ProfileActivityEntry[]
  outreach_pipeline: OutreachPipelineStatus
}

// ── Filter Profiles ──────────────────────────────────────────────────────

export interface FilterCriteria {
  logic: string
  version: number
  filters: Record<string, unknown>
}

export interface FilterProfileResponse {
  id: number
  profile_name: string
  county_fips: string[]
  description: string | null
  is_active: boolean
  version: number
  user_id: number | null
  filter_criteria: FilterCriteria
  rehab_cost_per_sqft: number
  min_comp_sales_for_arv: number
  comp_radius_miles: number
  comp_year_built_tolerance: number
  listing_type_priority: Record<string, unknown>
  deal_score_weights: Record<string, unknown>
  allow_automated_outreach: boolean
  max_outreach_attempts: number
  created_at: string
  updated_at: string
}

export interface FilterProfileCreateRequest {
  profile_name: string
  county_fips: string[]
  description?: string | null
  is_active?: boolean
  filter_criteria: FilterCriteria
  rehab_cost_per_sqft?: number
  min_comp_sales_for_arv?: number
  comp_radius_miles?: number
  comp_year_built_tolerance?: number
  listing_type_priority?: Record<string, unknown>
  deal_score_weights?: Record<string, unknown>
  allow_automated_outreach?: boolean
  max_outreach_attempts?: number
}

export interface FilterProfileUpdateRequest {
  profile_name?: string | null
  county_fips?: string[] | null
  description?: string | null
  is_active?: boolean | null
  filter_criteria?: FilterCriteria | null
  rehab_cost_per_sqft?: number | null
  min_comp_sales_for_arv?: number | null
  comp_radius_miles?: number | null
  comp_year_built_tolerance?: number | null
  listing_type_priority?: Record<string, unknown> | null
  deal_score_weights?: Record<string, unknown> | null
  allow_automated_outreach?: boolean | null
  max_outreach_attempts?: number | null
}

export interface CloneProfileRequest {
  profile_name: string
  county_fips?: string[] | null
}

// ── Inline search request (mirrors InlineSearchRequest on backend) ────────

export interface InlineSearchRequest {
  county_fips: string[]
  filter_criteria: FilterCriteria
  rehab_cost_per_sqft?: number
  min_comp_sales_for_arv?: number
  comp_radius_miles?: number
  comp_year_built_tolerance?: number
  deal_score_weights?: Record<string, unknown>
  sort_field?: string
  sort_direction?: 'ASC' | 'DESC'
  page?: number
  page_size?: number
}

// ── Properties ───────────────────────────────────────────────────────────

export interface ListingEventSummary {
  id: number
  signal_tier: number | null
  signal_type: string | null
  listing_type: string | null
  list_price: number | null
  list_date: string | null
  days_on_market: number | null
  arv_estimate: number | null
  arv_source: string | null
  arv_spread: number | null
  workflow_status: string
  source: string | null
  listing_url: string | null
}

export interface PropertySearchResult {
  county_fips: string
  parcel_id: string
  phy_addr1: string | null
  phy_city: string | null
  phy_zipcd: string | null
  dor_uc: string | null
  jv: number | null
  tot_lvg_area: number | null
  lnd_sqfoot: number | null
  act_yr_blt: number | null
  eff_yr_blt: number | null
  bedrooms: number | null
  bathrooms: number | null
  absentee_owner: boolean | null
  imp_qual: number | null
  years_since_last_sale: number | null
  improvement_to_land_ratio: number | null
  soh_compression_ratio: number | null
  arv_estimate: number | null
  arv_spread: number | null
  jv_per_sqft: number | null
  deal_score: number | null
  arv_source: string | null
  latitude: number | null
  longitude: number | null
  latest_listing: ListingEventSummary | null
}

export interface PaginatedPropertySearchResult {
  total: number
  page: number
  page_size: number
  total_pages: number
  results: PropertySearchResult[]
}

export interface PropertyDetail {
  county_fips: string
  parcel_id: string
  state_par_id: string
  phy_addr1: string | null
  phy_city: string | null
  phy_zipcd: string | null
  own_name: string | null
  own_addr1: string | null
  own_city: string | null
  own_state: string | null
  own_zipcd: string | null
  absentee_owner: boolean | null
  dor_uc: string | null
  pa_uc: string | null
  jv: number | null
  av_nsd: number | null
  lnd_val: number | null
  nav_total_assessment: number | null
  tot_lvg_area: number | null
  lnd_sqfoot: number | null
  act_yr_blt: number | null
  eff_yr_blt: number | null
  const_class: number | null
  imp_qual: number | null
  bedrooms: number | null
  bathrooms: number | null
  foundation_type: string | null
  exterior_wall: string | null
  roof_type: string | null
  cama_quality_code: string | null
  cama_condition_code: string | null
  no_buldng: number | null
  no_res_unts: number | null
  mkt_ar: string | null
  nbrhd_cd: string | null
  census_bk: string | null
  zoning: string | null
  years_since_last_sale: number | null
  improvement_to_land_ratio: number | null
  soh_compression_ratio: number | null
  spec_feat_val: number | null
  jv_per_sqft: number | null
  arv_estimate: number | null
  arv_spread: number | null
  qual_cd1: string | null
  sale_prc1: number | null
  sale_yr1: number | null
  sale_mo1: number | null
  qual_cd2: string | null
  sale_prc2: number | null
  sale_yr2: number | null
  sale_mo2: number | null
  latitude: number | null
  longitude: number | null
  nal_ingested_at: string | null
  cama_enriched_at: string | null
  latest_listing: ListingEventSummary | null
}
