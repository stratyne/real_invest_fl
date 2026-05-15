import { useEffect, useState, useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { getMe } from '../api/auth'
import { listCounties } from '../api/counties'
import { listProfiles, createProfile } from '../api/profiles'
import type {
  UserProfile,
  CountyResponse,
  FilterProfileResponse,
  FilterProfileCreateRequest,
} from '../types/api'

// ── Filter state type ─────────────────────────────────────────────────────

export interface FilterState {
  zip_codes: string[]
  mkt_ar_codes: string[]
  nbrhd_codes: string[]
  census_block_groups: string[]
  dor_use_code: number[]
  num_buildings_max: number | null
  num_residential_units_max: number | null
  just_value_min: number | null
  just_value_max: number | null
  assessed_value_min: number | null
  assessed_value_max: number | null
  land_value_min: number | null
  land_value_max: number | null
  nav_total_assessment_max: number | null
  list_price_to_jv_ratio_min: number | null
  list_price_to_jv_ratio_max: number | null
  living_area_sqft_min: number | null
  living_area_sqft_max: number | null
  lot_sqft_min: number | null
  lot_sqft_max: number | null
  year_built_min: number | null
  year_built_max: number | null
  effective_year_built_min: number | null
  effective_year_built_max: number | null
  bedrooms_exact: number | null
  bedrooms_min: number | null
  bedrooms_max: number | null
  bathrooms_exact: number | null
  bathrooms_min: number | null
  bathrooms_max: number | null
  imp_qual_min: number | null
  imp_qual_max: number | null
  ext_wall_codes: string[]
  foundation_codes: string[]
  special_feature_value_max: number | null
  absentee_owner: boolean | null
  homestead_status: boolean | null
  owner_state_dom_exclude: string[]
  years_since_last_sale_min: number | null
  years_since_last_sale_max: number | null
  prior_sale_qualification: string[]
  par_split_recent: boolean | null
  list_price_min: number | null
  list_price_max: number | null
  days_on_market_min: number | null
  days_on_market_max: number | null
  listing_types: string[]
  price_reduced: boolean | null
  min_arv_spread: number | null
  min_deal_score: number | null
  rehab_cost_per_sqft: number
  min_comp_sales_for_arv: number
  comp_radius_miles: number
  comp_year_built_tolerance: number
  max_results: number | null
  sort_by_field: string
  sort_by_direction: string
}

const EMPTY_FILTER: FilterState = {
  zip_codes: [],
  mkt_ar_codes: [],
  nbrhd_codes: [],
  census_block_groups: [],
  dor_use_code: [],
  num_buildings_max: null,
  num_residential_units_max: null,
  just_value_min: null,
  just_value_max: null,
  assessed_value_min: null,
  assessed_value_max: null,
  land_value_min: null,
  land_value_max: null,
  nav_total_assessment_max: null,
  list_price_to_jv_ratio_min: null,
  list_price_to_jv_ratio_max: null,
  living_area_sqft_min: null,
  living_area_sqft_max: null,
  lot_sqft_min: null,
  lot_sqft_max: null,
  year_built_min: null,
  year_built_max: null,
  effective_year_built_min: null,
  effective_year_built_max: null,
  bedrooms_exact: null,
  bedrooms_min: null,
  bedrooms_max: null,
  bathrooms_exact: null,
  bathrooms_min: null,
  bathrooms_max: null,
  imp_qual_min: null,
  imp_qual_max: null,
  ext_wall_codes: [],
  foundation_codes: [],
  special_feature_value_max: null,
  absentee_owner: null,
  homestead_status: null,
  owner_state_dom_exclude: [],
  years_since_last_sale_min: null,
  years_since_last_sale_max: null,
  prior_sale_qualification: [],
  par_split_recent: null,
  list_price_min: null,
  list_price_max: null,
  days_on_market_min: null,
  days_on_market_max: null,
  listing_types: [],
  price_reduced: null,
  min_arv_spread: null,
  min_deal_score: null,
  rehab_cost_per_sqft: 22.0,
  min_comp_sales_for_arv: 3,
  comp_radius_miles: 1.0,
  comp_year_built_tolerance: 15,
  max_results: null,
  sort_by_field: 'deal_score',
  sort_by_direction: 'DESC',
}

// ── Profile → FilterState hydration ──────────────────────────────────────

function profileToFilterState(p: FilterProfileResponse): FilterState {
  const f = p.filter_criteria.filters as Record<string, unknown>
  function range(key: string) { return (f[key] ?? {}) as Record<string, unknown> }
  function includeList(key: string): unknown[] { return ((f[key] as Record<string, unknown>)?.include as unknown[]) ?? [] }
  function numVal(key: string): number | null { return ((f[key] as Record<string, unknown>)?.value as number) ?? null }
  function boolReq(key: string): boolean | null { const v = (f[key] as Record<string, unknown>)?.required; return v == null ? null : Boolean(v) }
  function excludeList(key: string): string[] { return ((f[key] as Record<string, unknown>)?.exclude as string[]) ?? [] }

  return {
    zip_codes: (includeList('zip_codes') as string[]) ?? [],
    mkt_ar_codes: (includeList('mkt_ar_codes') as string[]) ?? [],
    nbrhd_codes: (includeList('nbrhd_codes') as string[]) ?? [],
    census_block_groups: (includeList('census_block_groups') as string[]) ?? [],
    dor_use_code: (includeList('dor_use_code') as number[]) ?? [],
    num_buildings_max: (range('num_buildings').max as number) ?? null,
    num_residential_units_max: (range('num_residential_units').max as number) ?? null,
    just_value_min: (range('just_value').min as number) ?? null,
    just_value_max: (range('just_value').max as number) ?? null,
    assessed_value_min: (range('assessed_value').min as number) ?? null,
    assessed_value_max: (range('assessed_value').max as number) ?? null,
    land_value_min: (range('land_value').min as number) ?? null,
    land_value_max: (range('land_value').max as number) ?? null,
    nav_total_assessment_max: (range('nav_total_assessment').max as number) ?? null,
    list_price_to_jv_ratio_min: (range('list_price_to_jv_ratio').min as number) ?? null,
    list_price_to_jv_ratio_max: (range('list_price_to_jv_ratio').max as number) ?? null,
    living_area_sqft_min: (range('living_area_sqft').min as number) ?? null,
    living_area_sqft_max: (range('living_area_sqft').max as number) ?? null,
    lot_sqft_min: (range('lot_sqft').min as number) ?? null,
    lot_sqft_max: (range('lot_sqft').max as number) ?? null,
    year_built_min: (range('year_built').min as number) ?? null,
    year_built_max: (range('year_built').max as number) ?? null,
    effective_year_built_min: (range('effective_year_built').min as number) ?? null,
    effective_year_built_max: (range('effective_year_built').max as number) ?? null,
    bedrooms_exact: (range('bedrooms').exact as number) ?? null,
    bedrooms_min: (range('bedrooms').min as number) ?? null,
    bedrooms_max: (range('bedrooms').max as number) ?? null,
    bathrooms_exact: (range('bathrooms').exact as number) ?? null,
    bathrooms_min: (range('bathrooms').min as number) ?? null,
    bathrooms_max: (range('bathrooms').max as number) ?? null,
    imp_qual_min: (range('imp_qual').min as number) ?? null,
    imp_qual_max: (range('imp_qual').max as number) ?? null,
    ext_wall_codes: (includeList('ext_wall_codes') as string[]) ?? [],
    foundation_codes: (includeList('foundation_codes') as string[]) ?? [],
    special_feature_value_max: (range('special_feature_value').max as number) ?? null,
    absentee_owner: boolReq('absentee_owner'),
    homestead_status: boolReq('homestead_status'),
    owner_state_dom_exclude: excludeList('owner_state_dom'),
    years_since_last_sale_min: (range('years_since_last_sale').min as number) ?? null,
    years_since_last_sale_max: (range('years_since_last_sale').max as number) ?? null,
    prior_sale_qualification: (includeList('prior_sale_qualification') as string[]) ?? [],
    par_split_recent: boolReq('par_split_recent'),
    list_price_min: (range('list_price').min as number) ?? null,
    list_price_max: (range('list_price').max as number) ?? null,
    days_on_market_min: (range('days_on_market').min as number) ?? null,
    days_on_market_max: (range('days_on_market').max as number) ?? null,
    listing_types: (includeList('listing_types') as string[]) ?? [],
    price_reduced: boolReq('price_reduced'),
    min_arv_spread: numVal('min_arv_spread'),
    min_deal_score: numVal('min_deal_score'),
    rehab_cost_per_sqft: p.rehab_cost_per_sqft,
    min_comp_sales_for_arv: p.min_comp_sales_for_arv,
    comp_radius_miles: p.comp_radius_miles,
    comp_year_built_tolerance: p.comp_year_built_tolerance,
    max_results: numVal('max_results'),
    sort_by_field: ((f['sort_by'] as Record<string, unknown>)?.field as string) ?? 'deal_score',
    sort_by_direction: ((f['sort_by'] as Record<string, unknown>)?.direction as string) ?? 'DESC',
  }
}

// ── FilterState → API payload ─────────────────────────────────────────────

export function filterStateToPayload(
  fs: FilterState,
  profileName: string,
  countyFips: string[],
): FilterProfileCreateRequest {
  return {
    profile_name: profileName,
    county_fips: countyFips,
    filter_criteria: {
      logic: 'AND',
      version: 1,
      filters: {
        sort_by: { field: fs.sort_by_field, direction: fs.sort_by_direction },
        zip_codes: { include: fs.zip_codes.length ? fs.zip_codes : null },
        mkt_ar_codes: { include: fs.mkt_ar_codes.length ? fs.mkt_ar_codes : null },
        nbrhd_codes: { include: fs.nbrhd_codes.length ? fs.nbrhd_codes : null },
        census_block_groups: { include: fs.census_block_groups.length ? fs.census_block_groups : null },
        dor_use_code: { include: fs.dor_use_code.length ? fs.dor_use_code : null },
        num_buildings: { max: fs.num_buildings_max },
        num_residential_units: { max: fs.num_residential_units_max },
        just_value: { min: fs.just_value_min, max: fs.just_value_max },
        assessed_value: { min: fs.assessed_value_min, max: fs.assessed_value_max },
        land_value: { min: fs.land_value_min, max: fs.land_value_max },
        nav_total_assessment: { max: fs.nav_total_assessment_max },
        list_price_to_jv_ratio: { min: fs.list_price_to_jv_ratio_min, max: fs.list_price_to_jv_ratio_max },
        living_area_sqft: { min: fs.living_area_sqft_min, max: fs.living_area_sqft_max },
        lot_sqft: { min: fs.lot_sqft_min, max: fs.lot_sqft_max },
        year_built: { min: fs.year_built_min, max: fs.year_built_max },
        effective_year_built: { min: fs.effective_year_built_min, max: fs.effective_year_built_max },
        bedrooms: { exact: fs.bedrooms_exact, min: fs.bedrooms_min, max: fs.bedrooms_max },
        bathrooms: { exact: fs.bathrooms_exact, min: fs.bathrooms_min, max: fs.bathrooms_max },
        imp_qual: { min: fs.imp_qual_min, max: fs.imp_qual_max },
        ext_wall_codes: { include: fs.ext_wall_codes.length ? fs.ext_wall_codes : null },
        foundation_codes: { include: fs.foundation_codes.length ? fs.foundation_codes : null },
        special_feature_value: { max: fs.special_feature_value_max },
        absentee_owner: { required: fs.absentee_owner },
        homestead_status: { required: fs.homestead_status },
        owner_state_dom: { exclude: fs.owner_state_dom_exclude.length ? fs.owner_state_dom_exclude : null },
        years_since_last_sale: { min: fs.years_since_last_sale_min, max: fs.years_since_last_sale_max },
        prior_sale_qualification: { include: fs.prior_sale_qualification.length ? fs.prior_sale_qualification : null },
        par_split_recent: { required: fs.par_split_recent },
        list_price: { min: fs.list_price_min, max: fs.list_price_max },
        days_on_market: { min: fs.days_on_market_min, max: fs.days_on_market_max },
        listing_types: { include: fs.listing_types.length ? fs.listing_types : null },
        price_reduced: { required: fs.price_reduced },
        min_arv_spread: { value: fs.min_arv_spread },
        min_deal_score: { value: fs.min_deal_score },
        max_results: { value: fs.max_results },
      },
    },
    rehab_cost_per_sqft: fs.rehab_cost_per_sqft,
    min_comp_sales_for_arv: fs.min_comp_sales_for_arv,
    comp_radius_miles: fs.comp_radius_miles,
    comp_year_built_tolerance: fs.comp_year_built_tolerance,
    deal_score_weights: {
      arv_spread_score: 0.5,
      signal_tier_score: 0.25,
      absentee_score: 0.25,
    },
  }
}

// ── Active filter count ───────────────────────────────────────────────────

function countActiveFilters(fs: FilterState): number {
  let count = 0
  if (fs.zip_codes.length) count++
  if (fs.mkt_ar_codes.length) count++
  if (fs.nbrhd_codes.length) count++
  if (fs.census_block_groups.length) count++
  if (fs.dor_use_code.length) count++
  if (fs.num_buildings_max != null) count++
  if (fs.num_residential_units_max != null) count++
  if (fs.just_value_min != null || fs.just_value_max != null) count++
  if (fs.assessed_value_min != null || fs.assessed_value_max != null) count++
  if (fs.land_value_min != null || fs.land_value_max != null) count++
  if (fs.nav_total_assessment_max != null) count++
  if (fs.list_price_to_jv_ratio_min != null || fs.list_price_to_jv_ratio_max != null) count++
  if (fs.living_area_sqft_min != null || fs.living_area_sqft_max != null) count++
  if (fs.lot_sqft_min != null || fs.lot_sqft_max != null) count++
  if (fs.year_built_min != null || fs.year_built_max != null) count++
  if (fs.effective_year_built_min != null || fs.effective_year_built_max != null) count++
  if (fs.bedrooms_exact != null || fs.bedrooms_min != null || fs.bedrooms_max != null) count++
  if (fs.bathrooms_exact != null || fs.bathrooms_min != null || fs.bathrooms_max != null) count++
  if (fs.imp_qual_min != null || fs.imp_qual_max != null) count++
  if (fs.ext_wall_codes.length) count++
  if (fs.foundation_codes.length) count++
  if (fs.special_feature_value_max != null) count++
  if (fs.absentee_owner != null) count++
  if (fs.homestead_status != null) count++
  if (fs.owner_state_dom_exclude.length) count++
  if (fs.years_since_last_sale_min != null || fs.years_since_last_sale_max != null) count++
  if (fs.prior_sale_qualification.length) count++
  if (fs.par_split_recent != null) count++
  if (fs.list_price_min != null || fs.list_price_max != null) count++
  if (fs.days_on_market_min != null || fs.days_on_market_max != null) count++
  if (fs.listing_types.length) count++
  if (fs.price_reduced != null) count++
  if (fs.min_arv_spread != null) count++
  if (fs.min_deal_score != null) count++
  return count
}

// ── Small reusable input components ──────────────────────────────────────

function NumInput({ label, value, onChange, placeholder }: {
  label: string; value: number | null; onChange: (v: number | null) => void; placeholder?: string
}) {
  return (
    <label style={inp.label}>
      <span style={inp.labelText}>{label}</span>
      <input style={inp.input} type="number" value={value ?? ''} placeholder={placeholder}
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))} />
    </label>
  )
}

function TextListInput({ label, value, onChange, placeholder, hint }: {
  label: string; value: (string | number)[]; onChange: (v: (string | number)[]) => void; placeholder?: string; hint?: string
}) {
  return (
    <label style={inp.label}>
      <span style={inp.labelText}>{label}</span>
      <input style={inp.input} type="text" value={value.join(', ')} placeholder={placeholder}
        onChange={(e) => {
          const raw = e.target.value
          if (!raw.trim()) { onChange([]); return }
          onChange(raw.split(',').map((s) => s.trim()).filter(Boolean))
        }} />
      {hint && <span style={inp.hint}>{hint}</span>}
    </label>
  )
}

function NumListInput({ label, value, onChange, placeholder, hint }: {
  label: string; value: number[]; onChange: (v: number[]) => void; placeholder?: string; hint?: string
}) {
  return (
    <label style={inp.label}>
      <span style={inp.labelText}>{label}</span>
      <input style={inp.input} type="text" value={value.join(', ')} placeholder={placeholder}
        onChange={(e) => {
          const raw = e.target.value
          if (!raw.trim()) { onChange([]); return }
          onChange(raw.split(',').map((s) => parseInt(s.trim(), 10)).filter((n) => !isNaN(n)))
        }} />
      {hint && <span style={inp.hint}>{hint}</span>}
    </label>
  )
}

function TriStateSelect({ label, value, onChange }: {
  label: string; value: boolean | null; onChange: (v: boolean | null) => void
}) {
  return (
    <label style={inp.label}>
      <span style={inp.labelText}>{label}</span>
      <select style={inp.select} value={value == null ? '' : value ? 'true' : 'false'}
        onChange={(e) => {
          if (e.target.value === '') onChange(null)
          else onChange(e.target.value === 'true')
        }}>
        <option value="">Any</option>
        <option value="true">Yes</option>
        <option value="false">No</option>
      </select>
    </label>
  )
}

// ── Collapsible section — row layout ─────────────────────────────────────

function Section({ title, children, defaultOpen = false }: {
  title: string; children: React.ReactNode; defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div style={sec.wrapper}>
      <button style={sec.header} onClick={() => setOpen((o) => !o)}>
        <span>{title}</span>
        <span style={sec.chevron}>{open ? '▾' : '▸'}</span>
      </button>
      {open && <div style={sec.body}>{children}</div>}
    </div>
  )
}

// ── Save modal ────────────────────────────────────────────────────────────

function SaveModal({ onSave, onClose, saving, error }: {
  onSave: (name: string) => Promise<void>; onClose: () => void; saving: boolean; error: string | null
}) {
  const [name, setName] = useState('')
  return (
    <div style={mod.overlay}>
      <div style={mod.modal}>
        <h3 style={mod.title}>Save Filter Profile</h3>
        <label style={inp.label}>
          <span style={inp.labelText}>Profile name</span>
          <input style={inp.input} value={name} onChange={(e) => setName(e.target.value)}
            autoFocus placeholder="e.g. Santa Rosa Residential" />
        </label>
        {error && <p style={mod.error}>{error}</p>}
        <div style={mod.actions}>
          <button style={mod.cancelBtn} onClick={onClose} disabled={saving}>Cancel</button>
          <button style={{ ...mod.saveBtn, opacity: !name.trim() || saving ? 0.6 : 1 }}
            onClick={() => name.trim() && onSave(name.trim())}
            disabled={!name.trim() || saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main SearchPage ───────────────────────────────────────────────────────

type NavState = { profileId?: number; countyFips?: string[]; filterState?: FilterState } | null

export default function SearchPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const navState = (location.state as NavState)

  const [user, setUser] = useState<UserProfile | null>(null)
  const [counties, setCounties] = useState<CountyResponse[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)

  const [selectedFips, setSelectedFips] = useState<string[]>(navState?.countyFips ?? [])
  const [profiles, setProfiles] = useState<FilterProfileResponse[]>([])
  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(navState?.profileId ?? null)
  const [filterState, setFilterState] = useState<FilterState>(navState?.filterState ?? EMPTY_FILTER)

  const [showSaveModal, setShowSaveModal] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null)

  const activeCount = countActiveFilters(filterState)
  const canSearch = activeCount >= 2 && selectedFips.length > 0
  const canSave = activeCount >= 2 && selectedFips.length > 0

  // ── On mount — load user and accessible counties
  useEffect(() => {
    Promise.all([getMe(), listCounties()])
      .then(([u, cs]) => { setUser(u); setCounties(cs) })
      .catch(() => setLoadError('Failed to load.'))
  }, [])

  // ── Load visible profiles once
  useEffect(() => {
    listProfiles()
      .then((ps) => {
        setProfiles(ps)

        const useNav =
          navState?.profileId != null

        if (useNav) {
          setSelectedProfileId(navState.profileId!)

          if (navState?.countyFips) {
            setSelectedFips(navState.countyFips)
          } else {
            setSelectedFips([])
          }

          if (navState?.filterState) {
            setFilterState(navState.filterState)
          } else {
            const target = ps.find((p) => p.id === navState.profileId) ?? null
            setFilterState(target ? profileToFilterState(target) : EMPTY_FILTER)
          }
        } else {
          setSelectedProfileId(null)
          setSelectedFips([])
          setFilterState(EMPTY_FILTER)
        }
      })
      .catch(() => setLoadError('Failed to load filter profiles.'))
  }, [location.state])

  function handleCountySelect(fips: string) {
    setSelectedFips((prev) =>
      prev.includes(fips)
        ? prev.filter((x) => x !== fips)
        : [...prev, fips]
    )
    setSelectedProfileId(null)
  }

  function handleProfileSelect(id: number | null) {
  if (id == null) {
    setSelectedProfileId(null)
    setSelectedFips([])
    setFilterState(EMPTY_FILTER)
    return
  }

  setSelectedProfileId(id)
  const p = profiles.find((x) => x.id === id)
  if (p) {
    setFilterState(profileToFilterState(p))
    setSelectedFips(p.county_fips)
  }
}

  const handleClearAll = useCallback(() => {
    setSelectedProfileId(null)
    setSelectedFips([])
    setFilterState(EMPTY_FILTER)
  }, [])

  const handleSave = useCallback(async (name: string) => {
    if (selectedFips.length === 0) return
    setSaving(true)
    setSaveError(null)
    try {
      const payload = filterStateToPayload(filterState, name, selectedFips)
      const created = await createProfile(payload)
      setProfiles((prev) => [...prev, created])
      setSelectedProfileId(created.id)
      setSelectedFips(created.county_fips)
      setShowSaveModal(false)
      setSaveSuccess(`Profile "${name}" saved.`)
      setTimeout(() => setSaveSuccess(null), 3000)
    } catch {
      setSaveError('Failed to save profile.')
    } finally {
      setSaving(false)
    }
  }, [filterState, selectedFips])

  function handleSearch() {
    if (!canSearch) return
    navigate('/results', {
      state: {
        profileId: selectedProfileId ?? undefined,
        filterState,
        countyFips: selectedFips,
      },
    })
  }

  function handleBack() {
    navigate('/dashboard')
  }

  function setFs(partial: Partial<FilterState>) {
    setFilterState((prev) => ({ ...prev, ...partial }))
  }

  if (loadError) return <div style={pg.centerMsg}>{loadError}</div>
  if (!user) return <div style={pg.centerMsg}>Loading…</div>

  return (
    <div style={pg.outer}>

      {/* ── Header ── */}
      <header style={pg.header}>
        <div style={pg.headerLeft}>
          <button style={pg.backBtn} onClick={handleBack}>← Dashboard</button>
          <span style={pg.brand}>Search</span>
        </div>
        <span style={pg.userName}>{user.full_name ?? user.email}</span>
      </header>

      <div style={pg.body}>

        {/* ── County picker ── */}
        <section style={pg.section}>
          <h2 style={pg.sectionTitle}>Counties</h2>
          <div style={pg.countyRow}>
            {counties.map((c) => (
              <button
                key={c.county_fips}
                style={{
                  ...pg.countyBtn,
                  ...(selectedFips.includes(c.county_fips) ? pg.countyBtnSelected : {}),
                }}
                onClick={() => handleCountySelect(c.county_fips)}
              >
                {c.county_name}
              </button>
            ))}
          </div>
        </section>

        {/* ── Profile picker ── */}
        <section style={pg.section}>
          <h2 style={pg.sectionTitle}>Filter Profile</h2>

          <div style={pg.profilePickerRow}>
            <select
              style={pg.profileSelect}
              value={selectedProfileId == null ? '' : String(selectedProfileId)}
              onChange={(e) => {
                const value = e.target.value

                if (value === '') {
                  setSelectedProfileId(null)
                  setSelectedFips([])
                  setFilterState(EMPTY_FILTER)
                  return
                }

                handleProfileSelect(Number(value))
              }}
            >
              <option value="">Select...</option>
              {profiles.map((p) => (
                <option key={p.id} value={String(p.id)}>
                  {p.profile_name}{p.user_id == null ? ' (system)' : ' (mine)'}
                </option>
              ))}
            </select>
          </div>

          <div style={{ marginTop: 8 }}>
            <button
              type="button"
              onClick={handleClearAll}
              style={{
                padding: '8px 12px',
                borderRadius: 8,
                border: '1px solid #d0d7de',
                background: '#fff',
                cursor: 'pointer',
                fontSize: 14,
              }}
            >
              Clear all
            </button>
          </div>

          {profiles.length === 0 && (
            <div style={{ marginTop: 8, fontSize: 14, color: '#6b7280' }}>
              No saved profiles available.
            </div>
          )}
        </section>

        {/* ── Filter editor ── */}
        {selectedFips.length > 0 && (
          <section style={pg.section}>
            <h2 style={pg.sectionTitle}>Filter Parameters</h2>
            <div style={pg.filterStack}>

              <Section title="Location" defaultOpen>
                <TextListInput label="ZIP Codes" value={filterState.zip_codes}
                  onChange={(v) => setFs({ zip_codes: v as string[] })} placeholder="e.g. 32501, 32502" />
                <TextListInput label="Market Area Codes" value={filterState.mkt_ar_codes}
                  onChange={(v) => setFs({ mkt_ar_codes: v as string[] })} placeholder="comma separated" />
                <TextListInput label="Neighbourhood Codes" value={filterState.nbrhd_codes}
                  onChange={(v) => setFs({ nbrhd_codes: v as string[] })} placeholder="comma separated" />
                <TextListInput label="Census Block Groups" value={filterState.census_block_groups}
                  onChange={(v) => setFs({ census_block_groups: v as string[] })} placeholder="comma separated" />
              </Section>

              <Section title="Property Type" defaultOpen>
                <NumListInput label="DOR Use Codes" value={filterState.dor_use_code}
                  onChange={(v) => setFs({ dor_use_code: v })} placeholder="e.g. 1"
                  hint="1 = Single family residential" />
                <NumInput label="Max Buildings" value={filterState.num_buildings_max}
                  onChange={(v) => setFs({ num_buildings_max: v })} />
                <NumInput label="Max Residential Units" value={filterState.num_residential_units_max}
                  onChange={(v) => setFs({ num_residential_units_max: v })} />
              </Section>

              <Section title="Valuation">
                <NumInput label="Just Value Min ($)" value={filterState.just_value_min} onChange={(v) => setFs({ just_value_min: v })} />
                <NumInput label="Just Value Max ($)" value={filterState.just_value_max} onChange={(v) => setFs({ just_value_max: v })} />
                <NumInput label="Assessed Value Min ($)" value={filterState.assessed_value_min} onChange={(v) => setFs({ assessed_value_min: v })} />
                <NumInput label="Assessed Value Max ($)" value={filterState.assessed_value_max} onChange={(v) => setFs({ assessed_value_max: v })} />
                <NumInput label="Land Value Min ($)" value={filterState.land_value_min} onChange={(v) => setFs({ land_value_min: v })} />
                <NumInput label="Land Value Max ($)" value={filterState.land_value_max} onChange={(v) => setFs({ land_value_max: v })} />
                <NumInput label="NAV Total Assessment Max ($)" value={filterState.nav_total_assessment_max} onChange={(v) => setFs({ nav_total_assessment_max: v })} />
                <NumInput label="List Price / JV Ratio Min" value={filterState.list_price_to_jv_ratio_min} onChange={(v) => setFs({ list_price_to_jv_ratio_min: v })} />
                <NumInput label="List Price / JV Ratio Max" value={filterState.list_price_to_jv_ratio_max} onChange={(v) => setFs({ list_price_to_jv_ratio_max: v })} />
              </Section>

              <Section title="Physical" defaultOpen>
                <NumInput label="Living Area Min (sqft)" value={filterState.living_area_sqft_min} onChange={(v) => setFs({ living_area_sqft_min: v })} />
                <NumInput label="Living Area Max (sqft)" value={filterState.living_area_sqft_max} onChange={(v) => setFs({ living_area_sqft_max: v })} />
                <NumInput label="Lot Size Min (sqft)" value={filterState.lot_sqft_min} onChange={(v) => setFs({ lot_sqft_min: v })} />
                <NumInput label="Lot Size Max (sqft)" value={filterState.lot_sqft_max} onChange={(v) => setFs({ lot_sqft_max: v })} />
                <NumInput label="Year Built Min" value={filterState.year_built_min} onChange={(v) => setFs({ year_built_min: v })} />
                <NumInput label="Year Built Max" value={filterState.year_built_max} onChange={(v) => setFs({ year_built_max: v })} />
                <NumInput label="Eff. Year Built Min" value={filterState.effective_year_built_min} onChange={(v) => setFs({ effective_year_built_min: v })} />
                <NumInput label="Eff. Year Built Max" value={filterState.effective_year_built_max} onChange={(v) => setFs({ effective_year_built_max: v })} />
                <NumInput label="Bedrooms (exact)" value={filterState.bedrooms_exact} onChange={(v) => setFs({ bedrooms_exact: v, bedrooms_min: null, bedrooms_max: null })} />
                <NumInput label="Bedrooms Min" value={filterState.bedrooms_min} onChange={(v) => setFs({ bedrooms_min: v, bedrooms_exact: null })} />
                <NumInput label="Bedrooms Max" value={filterState.bedrooms_max} onChange={(v) => setFs({ bedrooms_max: v, bedrooms_exact: null })} />
                <NumInput label="Bathrooms (exact)" value={filterState.bathrooms_exact} onChange={(v) => setFs({ bathrooms_exact: v, bathrooms_min: null, bathrooms_max: null })} />
                <NumInput label="Bathrooms Min" value={filterState.bathrooms_min} onChange={(v) => setFs({ bathrooms_min: v, bathrooms_exact: null })} />
                <NumInput label="Bathrooms Max" value={filterState.bathrooms_max} onChange={(v) => setFs({ bathrooms_max: v, bathrooms_exact: null })} />
                <NumInput label="Imp. Quality Min" value={filterState.imp_qual_min} onChange={(v) => setFs({ imp_qual_min: v })} />
                <NumInput label="Imp. Quality Max" value={filterState.imp_qual_max} onChange={(v) => setFs({ imp_qual_max: v })} />
                <TextListInput label="Exterior Wall Codes" value={filterState.ext_wall_codes}
                  onChange={(v) => setFs({ ext_wall_codes: v as string[] })} placeholder="comma separated" />
                <TextListInput label="Foundation Codes" value={filterState.foundation_codes}
                  onChange={(v) => setFs({ foundation_codes: v as string[] })} placeholder="comma separated" />
                <NumInput label="Special Feature Value Max ($)" value={filterState.special_feature_value_max} onChange={(v) => setFs({ special_feature_value_max: v })} />
              </Section>

              <Section title="Ownership">
                <TriStateSelect label="Absentee Owner" value={filterState.absentee_owner} onChange={(v) => setFs({ absentee_owner: v })} />
                <TriStateSelect label="Homestead" value={filterState.homestead_status} onChange={(v) => setFs({ homestead_status: v })} />
                <TextListInput label="Exclude Owner States" value={filterState.owner_state_dom_exclude}
                  onChange={(v) => setFs({ owner_state_dom_exclude: v as string[] })}
                  placeholder="e.g. FL, GA" hint="2-letter state codes to exclude" />
              </Section>

              <Section title="Sale History">
                <NumInput label="Years Since Last Sale Min" value={filterState.years_since_last_sale_min} onChange={(v) => setFs({ years_since_last_sale_min: v })} />
                <NumInput label="Years Since Last Sale Max" value={filterState.years_since_last_sale_max} onChange={(v) => setFs({ years_since_last_sale_max: v })} />
                <TextListInput label="Prior Sale Qual Codes" value={filterState.prior_sale_qualification}
                  onChange={(v) => setFs({ prior_sale_qualification: v as string[] })}
                  placeholder="e.g. 01, 02" hint="01 = arm's length · 02 = multi-parcel · 03 = foreclosure" />
                <TriStateSelect label="Recent Parcel Split" value={filterState.par_split_recent} onChange={(v) => setFs({ par_split_recent: v })} />
              </Section>

              <Section title="Listing">
                <NumInput label="List Price Min ($)" value={filterState.list_price_min} onChange={(v) => setFs({ list_price_min: v })} />
                <NumInput label="List Price Max ($)" value={filterState.list_price_max} onChange={(v) => setFs({ list_price_max: v })} />
                <NumInput label="Days on Market Min" value={filterState.days_on_market_min} onChange={(v) => setFs({ days_on_market_min: v })} />
                <NumInput label="Days on Market Max" value={filterState.days_on_market_max} onChange={(v) => setFs({ days_on_market_max: v })} />
                <TextListInput label="Listing Types" value={filterState.listing_types}
                  onChange={(v) => setFs({ listing_types: v as string[] })}
                  placeholder="e.g. FOR_SALE, FORECLOSURE" />
                <TriStateSelect label="Price Reduced" value={filterState.price_reduced} onChange={(v) => setFs({ price_reduced: v })} />
              </Section>

              <Section title="Deal Signals">
                <NumInput label="Min ARV Spread ($)" value={filterState.min_arv_spread} onChange={(v) => setFs({ min_arv_spread: v })} />
                <NumInput label="Min Deal Score (0–1)" value={filterState.min_deal_score} onChange={(v) => setFs({ min_deal_score: v })} />
              </Section>

              <Section title="ARV Engine">
                <NumInput label="Rehab Cost / sqft ($)" value={filterState.rehab_cost_per_sqft} onChange={(v) => setFs({ rehab_cost_per_sqft: v ?? 22 })} />
                <NumInput label="Min Comp Sales for ARV" value={filterState.min_comp_sales_for_arv} onChange={(v) => setFs({ min_comp_sales_for_arv: v ?? 3 })} />
                <NumInput label="Comp Radius (miles)" value={filterState.comp_radius_miles} onChange={(v) => setFs({ comp_radius_miles: v ?? 1.0 })} />
                <NumInput label="Comp Year Built Tolerance" value={filterState.comp_year_built_tolerance} onChange={(v) => setFs({ comp_year_built_tolerance: v ?? 15 })} />
              </Section>

              <Section title="Output">
                <NumInput label="Max Results" value={filterState.max_results}
                  onChange={(v) => setFs({ max_results: v })} placeholder="Leave blank for all" />
                <label style={inp.label}>
                  <span style={inp.labelText}>Sort By</span>
                  <select style={inp.select} value={filterState.sort_by_field}
                    onChange={(e) => setFs({ sort_by_field: e.target.value })}>
                    <option value="deal_score">Deal Score</option>
                    <option value="list_price">List Price</option>
                    <option value="just_value">Just Value</option>
                    <option value="arv_spread">ARV Spread</option>
                    <option value="year_built">Year Built</option>
                  </select>
                </label>
                <label style={inp.label}>
                  <span style={inp.labelText}>Direction</span>
                  <select style={inp.select} value={filterState.sort_by_direction}
                    onChange={(e) => setFs({ sort_by_direction: e.target.value })}>
                    <option value="DESC">Descending</option>
                    <option value="ASC">Ascending</option>
                  </select>
                </label>
              </Section>

            </div>

            {/* ── Actions bar ── */}
            <div style={pg.actionsBar}>
              <span style={pg.filterCount}>
                {activeCount} filter{activeCount !== 1 ? 's' : ''} active
                {activeCount < 2 && (
                  <span style={pg.filterCountWarning}> — minimum 2 required to search</span>
                )}
              </span>
              {saveSuccess && <span style={pg.saveSuccess}>{saveSuccess}</span>}
              <div style={pg.actionBtns}>
                <button
                    style={{ ...pg.saveBtn, opacity: canSave ? 1 : 0.5 }}
                    onClick={() => canSave && setShowSaveModal(true)}
                    disabled={!canSave}
                >
                    Save Filter
                </button>
                <button
                    style={{ ...pg.searchBtn, opacity: canSearch ? 1 : 0.5 }}
                    onClick={handleSearch}
                    disabled={!canSearch}
                >
                    Search
                </button>
                </div>
                {!canSearch && (
                <div style={{ marginTop: 8, fontSize: 14, color: '#6b7280' }}>
                    Select one or more counties, select a profile, and set at least 2 active filters.
                </div>
                )}
            </div>
          </section>
        )}

        {selectedFips.length === 0 && counties.length > 0 && (
          <div style={pg.centerMsg}>Select one or more counties above to configure filter parameters.</div>
        )}

      </div>

      {showSaveModal && (
        <SaveModal
          onSave={handleSave}
          onClose={() => { setShowSaveModal(false); setSaveError(null) }}
          saving={saving}
          error={saveError}
        />
      )}
    </div>
  )
}

// ── Styles ────────────────────────────────────────────────────────────────

const pg: Record<string, React.CSSProperties> = {
  outer: { minHeight: '100vh', background: 'var(--color-bg)', display: 'flex', flexDirection: 'column' },
  header: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '0 32px', height: '56px', background: 'var(--color-surface)',
    borderBottom: '1px solid var(--color-border)', flexShrink: 0,
  },
  headerLeft: { display: 'flex', alignItems: 'center', gap: '16px' },
  backBtn: {
    background: 'transparent', border: 'none', color: 'var(--color-text-muted)',
    fontSize: '13px', cursor: 'pointer', padding: '4px 0',
  },
  brand: { fontWeight: 700, fontSize: '16px' },
  userName: { color: 'var(--color-text-muted)', fontSize: '13px' },
  body: { padding: '32px', maxWidth: '800px', margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: '32px' },
  section: {},
  sectionTitle: { fontSize: '13px', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '12px' },
  countyRow: { display: 'flex', flexWrap: 'wrap', gap: '8px' },
  countyBtn: {
    background: 'var(--color-surface)', border: '1px solid var(--color-border)',
    borderRadius: '8px', padding: '10px 20px', fontSize: '13px', fontWeight: 500,
    color: 'var(--color-text)', cursor: 'pointer',
  },
  countyBtnSelected: { borderColor: 'var(--color-primary)', background: 'rgba(59,130,246,0.06)', color: 'var(--color-primary)' },
  profilePickerRow: { display: 'flex', alignItems: 'center', gap: '12px' },
  profileSelect: {
    background: 'var(--color-bg)', border: '1px solid var(--color-border)',
    borderRadius: '6px', color: 'var(--color-text)', padding: '8px 12px', fontSize: '13px',
    minWidth: '280px',
  },
  filterStack: { display: 'flex', flexDirection: 'column', gap: '8px' },
  actionsBar: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    marginTop: '20px', paddingTop: '16px', borderTop: '1px solid var(--color-border)',
    flexWrap: 'wrap', gap: '12px',
  },
  filterCount: { fontSize: '13px', color: 'var(--color-text-muted)' },
  filterCountWarning: { color: 'var(--color-warning)' },
  saveSuccess: { fontSize: '12px', color: 'var(--color-success)' },
  actionBtns: { display: 'flex', gap: '10px' },
  saveBtn: {
    background: 'transparent', border: '1px solid var(--color-border)',
    borderRadius: '6px', color: 'var(--color-text)', padding: '10px 20px',
    fontWeight: 600, fontSize: '13px', cursor: 'pointer',
  },
  searchBtn: {
    background: 'var(--color-primary)', border: 'none', borderRadius: '6px',
    color: '#fff', padding: '10px 24px', fontWeight: 600, fontSize: '13px', cursor: 'pointer',
  },
  centerMsg: { padding: '40px', textAlign: 'center', color: 'var(--color-text-muted)', fontSize: '14px' },
}

// Section body: row layout — wrapping flex instead of column
const sec: Record<string, React.CSSProperties> = {
  wrapper: { border: '1px solid var(--color-border)', borderRadius: '8px', overflow: 'hidden' },
  header: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '10px 14px', background: 'var(--color-bg)', border: 'none',
    color: 'var(--color-text)', fontWeight: 600, fontSize: '12px', width: '100%',
    cursor: 'pointer', textTransform: 'uppercase', letterSpacing: '0.05em',
  },
  chevron: { fontSize: '12px', color: 'var(--color-text-muted)' },
  body: {
    padding: '12px 14px',
    display: 'flex',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: '10px',
    background: 'var(--color-surface)',
  },
}

const inp: Record<string, React.CSSProperties> = {
  label: { display: 'flex', flexDirection: 'column', gap: '4px', minWidth: '180px', flex: '1 1 180px' },
  labelText: { fontSize: '11px', color: 'var(--color-text-muted)', fontWeight: 500 },
  input: {
    background: 'var(--color-bg)', border: '1px solid var(--color-border)',
    borderRadius: '5px', padding: '7px 10px', color: 'var(--color-text)',
    fontSize: '12px', outline: 'none',
  },
  select: {
    background: 'var(--color-bg)', border: '1px solid var(--color-border)',
    borderRadius: '5px', padding: '7px 10px', color: 'var(--color-text)',
    fontSize: '12px', outline: 'none',
  },
  hint: { fontSize: '10px', color: 'var(--color-text-muted)' },
}

const mod: Record<string, React.CSSProperties> = {
  overlay: {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 200,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
  },
  modal: {
    background: 'var(--color-surface)', border: '1px solid var(--color-border)',
    borderRadius: '12px', padding: '28px', width: '380px',
    display: 'flex', flexDirection: 'column', gap: '16px',
  },
  title: { fontSize: '16px', fontWeight: 700 },
  error: { color: 'var(--color-danger)', fontSize: '12px' },
  actions: { display: 'flex', justifyContent: 'flex-end', gap: '10px' },
  cancelBtn: {
    background: 'transparent', border: '1px solid var(--color-border)',
    borderRadius: '6px', color: 'var(--color-text)', padding: '8px 16px', fontSize: '13px', cursor: 'pointer',
  },
  saveBtn: {
    background: 'var(--color-primary)', border: 'none', borderRadius: '6px',
    color: '#fff', padding: '8px 16px', fontSize: '13px', fontWeight: 600, cursor: 'pointer',
  },
}
