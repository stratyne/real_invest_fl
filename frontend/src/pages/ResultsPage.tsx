import { useEffect, useState, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import Map, { Popup, Marker, type MapRef } from 'react-map-gl/maplibre'
import 'maplibre-gl/dist/maplibre-gl.css'
import AppNav from '../components/AppNav'
import { searchProperties, searchPropertiesInline, getProperty } from '../api/properties'
import { createProfile } from '../api/profiles'
import type {
  PropertySearchResult,
  PropertyDetail,
  InlineSearchRequest,
  FilterCriteria,
} from '../types/api'
import type { FilterState } from './SearchPage'
import { filterStateToPayload } from './SearchPage'

const PAGE_SIZE = 25

// ── Helpers ───────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined, prefix = ''): string {
  if (n == null) return '—'
  return prefix + n.toLocaleString()
}

function fmtFloat(n: number | null | undefined, decimals = 2): string {
  if (n == null) return '—'
  return n.toFixed(decimals)
}

function ArvBadge({ source }: { source: string | null }) {
  if (!source) return <span style={{ color: 'var(--color-text-muted)' }}>—</span>
  if (source === 'COMP') return <span className="badge badge--comp">COMP</span>
  if (source === 'NAL_COMP') return <span className="badge badge--nal-comp">NAL COMP</span>
  return <span className="badge badge--jv-fallback">JV Fallback</span>
}

// ── Property detail drawer ────────────────────────────────────────────────

function DrawerSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={drawerStyles.section}>
      <div style={drawerStyles.sectionTitle}>{title}</div>
      {children}
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={drawerStyles.row}>
      <span style={drawerStyles.rowLabel}>{label}</span>
      <span style={drawerStyles.rowValue}>{value ?? '—'}</span>
    </div>
  )
}

interface DrawerProps {
  countyFips: string
  parcelId: string
  onClose: () => void
  onLocate: (() => void) | null
}

function PropertyDrawer({ countyFips, parcelId, onClose, onLocate }: DrawerProps) {
  const [detail, setDetail] = useState<PropertyDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setDetail(null)
    setError(null)

    getProperty(countyFips, parcelId)
      .then((data) => { if (active) setDetail(data) })
      .catch(() => { if (active) setError('Failed to load property detail.') })

    return () => { active = false }
  }, [countyFips, parcelId])

  return (
    <div style={drawerStyles.overlay} onClick={onClose}>
      <div style={drawerStyles.drawer} onClick={(e) => e.stopPropagation()}>
        <div style={drawerStyles.header}>
          <h3 style={drawerStyles.title}>Property Detail</h3>
          <button style={drawerStyles.closeBtn} onClick={onClose}>✕</button>
        </div>
        {error && <p style={{ padding: '20px', color: 'var(--color-danger)' }}>{error}</p>}
        {!detail && !error && <p style={{ padding: '20px', color: 'var(--color-text-muted)' }}>Loading…</p>}
        {detail && (
          <div style={drawerStyles.body}>
            {onLocate && (
              <button style={drawerStyles.locateBtn} onClick={onLocate}>
                📍 See on map
              </button>
            )}
            <p style={drawerStyles.address}>
              {detail.phy_addr1 ?? '—'}<br />
              {detail.phy_city ?? '—'}, FL {detail.phy_zipcd ?? '—'}
            </p>
            <DrawerSection title="Ownership">
              <Row label="Owner" value={detail.own_name} />
              <Row label="Mailing" value={[detail.own_addr1, detail.own_city, detail.own_state, detail.own_zipcd].filter(Boolean).join(', ')} />
              <Row label="Absentee" value={detail.absentee_owner == null ? '—' : detail.absentee_owner ? 'Yes' : 'No'} />
            </DrawerSection>
            <DrawerSection title="Valuation">
              <Row label="Just Value" value={fmt(detail.jv, '$')} />
              <Row label="Assessed Value" value={fmt(detail.av_nsd, '$')} />
              <Row label="Land Value" value={fmt(detail.lnd_val, '$')} />
              <Row label="JV / sqft" value={detail.jv_per_sqft != null ? `$${fmtFloat(detail.jv_per_sqft)}` : '—'} />
              <Row label="ARV Estimate" value={
                detail.arv_estimate != null
                  ? <>
                      {fmt(detail.arv_estimate, '$')}
                      {(detail.latest_listing?.arv_source ?? detail.arv_source) &&
                        <> <ArvBadge source={detail.latest_listing?.arv_source ?? detail.arv_source ?? null} /></>
                      }
                    </>
                  : '—'
              } />
              <Row label="ARV Spread" value={fmt(detail.arv_spread, '$')} />
              <Row label="ARV Source" value={detail.latest_listing?.arv_source ?? detail.arv_source ?? '—'} />
            </DrawerSection>
            <DrawerSection title="Property">
              <Row label="DOR Use Code" value={detail.dor_uc} />
              <Row label="Year Built" value={detail.act_yr_blt} />
              <Row label="Eff. Year Built" value={detail.eff_yr_blt} />
              <Row label="Living Area" value={detail.tot_lvg_area != null ? `${detail.tot_lvg_area.toLocaleString()} sqft` : '—'} />
              <Row label="Lot Size" value={detail.lnd_sqfoot != null ? `${detail.lnd_sqfoot.toLocaleString()} sqft` : '—'} />
              <Row label="Bedrooms" value={detail.bedrooms} />
              <Row label="Bathrooms" value={detail.bathrooms} />
              <Row label="Buildings" value={detail.no_buldng} />
              <Row label="Res. Units" value={detail.no_res_unts} />
              <Row label="Imp. Quality" value={detail.imp_qual} />
              <Row label="Zoning" value={detail.zoning} />
            </DrawerSection>
            <DrawerSection title="CAMA">
              <Row label="Quality Code" value={detail.cama_quality_code} />
              <Row label="Condition Code" value={detail.cama_condition_code} />
              <Row label="Foundation" value={detail.foundation_type} />
              <Row label="Exterior Wall" value={detail.exterior_wall} />
              <Row label="Roof Type" value={detail.roof_type} />
              <Row label="CAMA Enriched" value={detail.cama_enriched_at ? new Date(detail.cama_enriched_at).toLocaleDateString() : 'Not enriched'} />
            </DrawerSection>
            <DrawerSection title="Sale History">
              {detail.sale_history.length === 0 ? (
                <Row label="No sale history" value="—" />
              ) : (
                detail.sale_history.map((s, i) => (
                  <div key={i} style={{ paddingBottom: '8px', borderBottom: i < detail.sale_history.length - 1 ? '1px solid var(--color-border)' : 'none', marginBottom: i < detail.sale_history.length - 1 ? '8px' : 0 }}>
                    <Row label="Date" value={s.sale_date ?? '—'} />
                    <Row label="Price" value={s.sale_price != null ? fmt(s.sale_price, '$') : '—'} />
                    <Row label="Instrument" value={s.instrument_type ?? '—'} />
                    <Row label="Qual Code" value={s.qualification_code ?? '—'} />
                    <Row label="Type" value={s.sale_type ?? '—'} />
                    <Row label="Grantor" value={s.grantor || '—'} />
                    <Row label="Grantee" value={s.grantee || '—'} />
                    <Row label="$/sqft" value={s.price_per_sqft != null ? `$${s.price_per_sqft.toFixed(2)}` : '—'} />
                    <Row label="Source" value={s.source} />
                  </div>
                ))
              )}
            </DrawerSection>
            <DrawerSection title="Ratios">
              <Row label="Imp / Land Ratio" value={detail.improvement_to_land_ratio != null ? fmtFloat(detail.improvement_to_land_ratio, 4) : '—'} />
              <Row label="SOH Compression" value={detail.soh_compression_ratio != null ? fmtFloat(detail.soh_compression_ratio, 4) : '—'} />
            </DrawerSection>
            {detail.latest_listing && (
              <DrawerSection title="Latest Signal">
                <Row label="Type" value={detail.latest_listing.listing_type} />
                <Row label="Signal Tier" value={detail.latest_listing.signal_tier} />
                <Row label="Signal Type" value={detail.latest_listing.signal_type} />
                <Row label="List Price" value={fmt(detail.latest_listing.list_price, '$')} />
                <Row label="Days on Market" value={detail.latest_listing.days_on_market} />
                <Row label="Status" value={detail.latest_listing.workflow_status} />
                <Row label="Source" value={detail.latest_listing.source} />
                {detail.latest_listing.listing_url && (
                  <Row label="URL" value={<a href={detail.latest_listing.listing_url} target="_blank" rel="noreferrer">View listing</a>} />
                )}
              </DrawerSection>
            )}
            <div style={drawerStyles.parcelId}>Parcel ID: {detail.parcel_id}</div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Save modal ────────────────────────────────────────────────────────────

interface SaveModalProps {
  onSave: (name: string) => Promise<void>
  onClose: () => void
  saving: boolean
  error: string | null
}

function SaveModal({ onSave, onClose, saving, error }: SaveModalProps) {
  const [name, setName] = useState('')
  return (
    <div style={saveModalStyles.overlay}>
      <div style={saveModalStyles.modal}>
        <h3 style={saveModalStyles.title}>Save Filter Profile</h3>
        <label style={saveModalStyles.label}>
          <span style={saveModalStyles.labelText}>Profile name</span>
          <input
            style={saveModalStyles.input}
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
            placeholder="e.g. Santa Rosa Residential"
          />
        </label>
        {error && <p style={{ color: 'var(--color-danger)', fontSize: '12px' }}>{error}</p>}
        <div style={saveModalStyles.actions}>
          <button style={saveModalStyles.cancelBtn} onClick={onClose} disabled={saving}>Cancel</button>
          <button
            style={{ ...saveModalStyles.saveBtn, opacity: !name.trim() || saving ? 0.6 : 1 }}
            onClick={() => name.trim() && onSave(name.trim())}
            disabled={!name.trim() || saving}
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Build inline search request from FilterState ──────────────────────────

function buildInlineRequest(
  filterState: FilterState,
  countyFips: string[],
  page: number,
  pageSize: number,
  sortField: string,
  sortDirection: 'ASC' | 'DESC',
): InlineSearchRequest {
  const payload = filterStateToPayload(filterState, '__inline__', countyFips)
  return {
    county_fips: countyFips,
    filter_criteria: payload.filter_criteria as FilterCriteria,
    rehab_cost_per_sqft: payload.rehab_cost_per_sqft,
    min_comp_sales_for_arv: payload.min_comp_sales_for_arv,
    comp_radius_miles: payload.comp_radius_miles,
    comp_year_built_tolerance: payload.comp_year_built_tolerance,
    deal_score_weights: payload.deal_score_weights,
    sort_field: sortField,
    sort_direction: sortDirection,
    page,
    page_size: pageSize,
  }
}

// ── Main ResultsPage ──────────────────────────────────────────────────────

export default function ResultsPage() {
  const navigate = useNavigate()
  const location = useLocation()

  const locationState = location.state as {
    profileId?: number
    filterState: FilterState | null
    countyFips: string[]
  } | null

  const mapRef = useRef<MapRef | null>(null)

  const filterState: FilterState | null = locationState?.filterState ?? null
  const countyFips: string[] = locationState?.countyFips ?? []
  const profileId: number | undefined = locationState?.profileId

  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [pageResults, setPageResults] = useState<PropertySearchResult[]>([])

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedResult, setSelectedResult] = useState<PropertySearchResult | null>(null)
  const [popupResult, setPopupResult] = useState<PropertySearchResult | null>(null)

  const [showSaveModal, setShowSaveModal] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null)

  const [sortField, setSortField] = useState<string>(filterState?.sort_by_field ?? 'deal_score')
  const [sortDirection, setSortDirection] = useState<'ASC' | 'DESC'>((filterState?.sort_by_direction as 'ASC' | 'DESC') ?? 'DESC')

  // We need the user for the nav bar — fetch it
  const [userName, setUserName] = useState<string | undefined>(undefined)
  useEffect(() => {
    import('../api/auth').then(({ getMe }) => {
      getMe().then((u) => setUserName(u.full_name ?? u.email)).catch(() => undefined)
    })
  }, [])

  useEffect(() => {
    setSortField(filterState?.sort_by_field ?? 'deal_score')
    setSortDirection((filterState?.sort_by_direction as 'ASC' | 'DESC') ?? 'DESC')
    setPage(1)
  }, [location.state]) // eslint-disable-line react-hooks/exhaustive-deps

  function centerMapOnResult(r: PropertySearchResult) {
    if (r.latitude == null || r.longitude == null) return
    mapRef.current?.getMap().easeTo({
      center: [r.longitude, r.latitude],
      zoom: 15,
      duration: 800,
      essential: true,
    })
  }

  function handleLocateSelectedResult(r: PropertySearchResult) {
    centerMapOnResult(r)
    setPopupResult(r)
    setSelectedResult(null)
  }

  function handleSortClick(field: string) {
    if (!filterState && profileId == null) return
    if (field === sortField) {
      setSortDirection((d) => (d === 'DESC' ? 'ASC' : 'DESC'))
    } else {
      setSortField(field)
      setSortDirection('DESC')
    }
    setPage(1)
  }

  function SortIndicator({ field }: { field: string }) {
    if (field !== sortField) {
      return <span style={{ color: 'var(--color-border)', marginLeft: 4 }}>⇅</span>
    }
    return <span style={{ marginLeft: 4 }}>{sortDirection === 'DESC' ? '↓' : '↑'}</span>
  }

  useEffect(() => {
    if (profileId == null && (!filterState || countyFips.length === 0)) {
      setError('No filter state available. Return to search and try again.')
      setLoading(false)
      return
    }

    setLoading(true)
    setPopupResult(null)
    setSelectedResult(null)

    const run = (profileId != null && filterState == null)
      ? searchProperties(profileId, page, PAGE_SIZE, sortField, sortDirection)
      : searchPropertiesInline(
          buildInlineRequest(filterState!, countyFips, page, PAGE_SIZE, sortField, sortDirection),
        )

    run
      .then((data) => {
        setPageResults(data.results)
        setTotal(data.total)
        setTotalPages(data.total_pages)
        setLoading(false)
      })
      .catch(() => {
        setError('Search failed.')
        setLoading(false)
      })
  }, [page, sortField, sortDirection]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleEditFilter() {
    navigate('/search', {
      state: { profileId, countyFips, filterState },
    })
  }

  async function handleSave(name: string) {
    if (!filterState || countyFips.length === 0) return
    setSaving(true)
    setSaveError(null)
    try {
      const payload = filterStateToPayload(filterState, name, countyFips)
      await createProfile(payload)
      setShowSaveModal(false)
      setSaveSuccess(`Profile "${name}" saved.`)
      setTimeout(() => setSaveSuccess(null), 3000)
    } catch {
      setSaveError('Failed to save profile.')
    } finally {
      setSaving(false)
    }
  }

  const MAP_CENTER = { longitude: -87.0, latitude: 30.65, zoom: 8 }

  return (
    <div style={pageStyles.outer}>
      <AppNav userName={userName} />

      {/* Page sub-header */}
      <div style={pageStyles.subHeader}>
        <div style={pageStyles.subHeaderLeft}>
          <button style={pageStyles.editBtn} onClick={handleEditFilter}>
            ← Edit Filter
          </button>
          {!loading && (
            <span style={pageStyles.resultCount}>
              {total.toLocaleString()} result{total !== 1 ? 's' : ''}
              {totalPages > 1 && ` — page ${page} of ${totalPages}`}
            </span>
          )}
        </div>
        <div style={pageStyles.subHeaderRight}>
          {saveSuccess && <span style={pageStyles.saveSuccess}>{saveSuccess}</span>}
          <button
            style={{ ...pageStyles.saveBtn, opacity: !filterState ? 0.5 : 1 }}
            onClick={() => filterState && setShowSaveModal(true)}
            disabled={!filterState}
          >
            Save Filter
          </button>
        </div>
      </div>

      {/* Body */}
      <div style={pageStyles.body}>
        {/* Results table */}
        <div style={pageStyles.tablePanel}>
          {loading && <p style={pageStyles.msg}>Searching…</p>}
          {error && <p style={{ ...pageStyles.msg, color: 'var(--color-danger)' }}>{error}</p>}
          {!loading && !error && total === 0 && (
            <p style={pageStyles.msg}>No properties matched the filter criteria.</p>
          )}

          {!loading && !error && pageResults.length > 0 && (
            <>
              <div style={pageStyles.tableWrapper}>
                <table style={pageStyles.table}>
                  <thead>
                    <tr>
                      <th style={{ ...pageStyles.th, ...pageStyles.thSortable }} onClick={() => handleSortClick('address')}>
                        Address<SortIndicator field="address" />
                      </th>
                      <th style={{ ...pageStyles.th, ...pageStyles.thSortable }} onClick={() => handleSortClick('jv')}>
                        JV<SortIndicator field="jv" />
                      </th>
                      <th style={{ ...pageStyles.th, ...pageStyles.thSortable }} onClick={() => handleSortClick('arv_spread')}>
                        ARV<SortIndicator field="arv_spread" />
                      </th>
                      <th style={{ ...pageStyles.th, ...pageStyles.thSortable }} onClick={() => handleSortClick('arv_source')}>
                        Source<SortIndicator field="arv_source" />
                      </th>
                      <th style={{ ...pageStyles.th, ...pageStyles.thSortable }} onClick={() => handleSortClick('arv_spread')}>
                        Spread<SortIndicator field="arv_spread" />
                      </th>
                      <th style={{ ...pageStyles.th, ...pageStyles.thSortable }} onClick={() => handleSortClick('tot_lvg_area')}>
                        Sqft<SortIndicator field="tot_lvg_area" />
                      </th>
                      <th style={{ ...pageStyles.th, ...pageStyles.thSortable }} onClick={() => handleSortClick('act_yr_blt')}>
                        Yr Blt<SortIndicator field="act_yr_blt" />
                      </th>
                      <th style={{ ...pageStyles.th, ...pageStyles.thSortable }} onClick={() => handleSortClick('deal_score')}>
                        Score<SortIndicator field="deal_score" />
                      </th>
                      <th style={{ ...pageStyles.th, ...pageStyles.thSortable }} onClick={() => handleSortClick('signal_tier')}>
                        Signal<SortIndicator field="signal_tier" />
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {pageResults.map((r) => (
                      <tr
                        key={`${r.county_fips}:${r.parcel_id}`}
                        id={`row-${r.county_fips}-${r.parcel_id}`}
                        style={{
                          ...pageStyles.tr,
                          ...(selectedResult?.county_fips === r.county_fips &&
                          selectedResult?.parcel_id === r.parcel_id
                            ? pageStyles.trSelected
                            : {}),
                        }}
                        onClick={() => setSelectedResult(r)}
                      >
                        <td style={pageStyles.td}>
                          <div style={pageStyles.addrLine1}>{r.phy_addr1 ?? '—'}</div>
                          <div style={pageStyles.addrLine2}>{r.phy_city ?? '—'}, {r.phy_zipcd ?? '—'}</div>
                        </td>
                        <td style={pageStyles.td}>{fmt(r.jv, '$')}</td>
                        <td style={pageStyles.td}>{fmt(r.arv_estimate, '$')}</td>
                        <td style={pageStyles.td}><ArvBadge source={r.arv_source} /></td>
                        <td style={pageStyles.td}>{fmt(r.arv_spread, '$')}</td>
                        <td style={pageStyles.td}>{r.tot_lvg_area != null ? r.tot_lvg_area.toLocaleString() : '—'}</td>
                        <td style={pageStyles.td}>{r.act_yr_blt ?? '—'}</td>
                        <td style={pageStyles.td}>
                          {r.deal_score != null
                            ? <span style={{ color: 'var(--color-success)', fontWeight: 600 }}>{(r.deal_score * 100).toFixed(1)}</span>
                            : <span style={{ color: 'var(--color-text-muted)' }}>—</span>
                          }
                        </td>
                        <td style={pageStyles.td}>
                          {r.latest_listing
                            ? <span style={pageStyles.tierBadge}>T{r.latest_listing.signal_tier} {r.latest_listing.signal_type ?? ''}</span>
                            : '—'
                          }
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <div style={pageStyles.pagination}>
                <button style={pageStyles.pageBtn} onClick={() => setPage(1)} disabled={page === 1 || loading}>«</button>
                <button style={pageStyles.pageBtn} onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1 || loading}>‹ Prev</button>

                {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                  let pageNum: number
                  if (totalPages <= 7) { pageNum = i + 1 }
                  else if (page <= 4) { pageNum = i + 1 }
                  else if (page >= totalPages - 3) { pageNum = totalPages - 6 + i }
                  else { pageNum = page - 3 + i }
                  return (
                    <button
                      key={pageNum}
                      style={{ ...pageStyles.pageBtn, ...(pageNum === page ? pageStyles.pageBtnActive : {}) }}
                      onClick={() => setPage(pageNum)}
                      disabled={loading}
                    >
                      {pageNum}
                    </button>
                  )
                })}

                <button style={pageStyles.pageBtn} onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages || loading}>Next ›</button>
                <button style={pageStyles.pageBtn} onClick={() => setPage(totalPages)} disabled={page === totalPages || loading}>»</button>

                <span style={pageStyles.pageInfo}>
                  {((page - 1) * PAGE_SIZE) + 1}–{Math.min(page * PAGE_SIZE, total)} of {total.toLocaleString()}
                </span>
              </div>
            </>
          )}
        </div>

        {/* Map panel */}
        <div style={pageStyles.mapPanel}>
          <Map
            ref={mapRef}
            initialViewState={MAP_CENTER}
            style={{ width: '100%', height: '100%' }}
            mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
          >
            {pageResults
              .filter((r) => r.latitude != null && r.longitude != null)
              .map((r) => (
                <Marker
                  key={`${r.county_fips}:${r.parcel_id}`}
                  longitude={r.longitude!}
                  latitude={r.latitude!}
                  onClick={() => {
                    centerMapOnResult(r)
                    setPopupResult(r)
                    setSelectedResult(r)
                    document.getElementById(`row-${r.county_fips}-${r.parcel_id}`)?.scrollIntoView({
                      behavior: 'smooth',
                      block: 'nearest',
                    })
                  }}
                  style={{ cursor: 'pointer' }}
                />
              ))
            }

            {popupResult && (
              <Popup
                longitude={popupResult.longitude!}
                latitude={popupResult.latitude!}
                anchor="bottom"
                onClose={() => setPopupResult(null)}
                closeOnClick={false}
              >
                <div style={{ color: '#000', fontSize: '12px', lineHeight: 1.5 }}>
                  <strong>{popupResult.phy_addr1}</strong><br />
                  JV: {fmt(popupResult.jv, '$')}<br />
                  ARV: {fmt(popupResult.arv_estimate, '$')}
                </div>
              </Popup>
            )}
          </Map>
        </div>
      </div>

      {/* Property drawer */}
      {selectedResult && (
        <PropertyDrawer
          countyFips={selectedResult.county_fips}
          parcelId={selectedResult.parcel_id}
          onClose={() => setSelectedResult(null)}
          onLocate={
            selectedResult.latitude != null && selectedResult.longitude != null
              ? () => handleLocateSelectedResult(selectedResult)
              : null
          }
        />
      )}

      {/* Save modal */}
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

const pageStyles: Record<string, React.CSSProperties> = {
  outer: {
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    overflow: 'hidden',
    background: 'var(--color-bg)',
  },
  subHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 20px',
    height: '44px',
    background: 'var(--color-surface)',
    borderBottom: '1px solid var(--color-border)',
    flexShrink: 0,
    gap: '16px',
  },
  subHeaderLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
  },
  subHeaderRight: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  editBtn: {
    background: 'transparent',
    border: 'none',
    color: 'var(--color-primary)',
    fontSize: '13px',
    padding: '4px 0',
    whiteSpace: 'nowrap',
    cursor: 'pointer',
  },
  resultCount: {
    fontSize: '12px',
    color: 'var(--color-text-muted)',
  },
  saveSuccess: { fontSize: '12px', color: 'var(--color-success)' },
  saveBtn: {
    background: 'transparent',
    border: '1px solid var(--color-border)',
    borderRadius: '6px',
    color: 'var(--color-text)',
    padding: '6px 14px',
    fontWeight: 600,
    fontSize: '12px',
    cursor: 'pointer',
  },
  body: { display: 'flex', flex: 1, overflow: 'hidden' },
  tablePanel: { flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' },
  tableWrapper: { overflowX: 'auto', flex: 1 },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: '12px' },
  th: {
    padding: '10px 12px',
    textAlign: 'left',
    fontWeight: 600,
    color: 'var(--color-text-muted)',
    borderBottom: '1px solid var(--color-border)',
    background: 'var(--color-surface)',
    position: 'sticky',
    top: 0,
    zIndex: 1,
  },
  thSortable: { cursor: 'pointer', userSelect: 'none' as const },
  tr: {
    borderBottom: '1px solid var(--color-border)',
    cursor: 'pointer',
    transition: 'background 0.1s',
  },
  trSelected: { background: 'rgba(59,130,246,0.25)' },
  td: { padding: '10px 12px', verticalAlign: 'middle' },
  addrLine1: { fontWeight: 500 },
  addrLine2: { color: 'var(--color-text-muted)', fontSize: '11px' },
  tierBadge: { fontSize: '10px', color: 'var(--color-text-muted)' },
  msg: { padding: '40px', textAlign: 'center', color: 'var(--color-text-muted)' },
  pagination: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    padding: '12px 16px',
    borderTop: '1px solid var(--color-border)',
    flexShrink: 0,
    flexWrap: 'wrap',
  },
  pageBtn: {
    background: 'var(--color-surface)',
    border: '1px solid var(--color-border)',
    borderRadius: '5px',
    color: 'var(--color-text)',
    padding: '5px 10px',
    fontSize: '12px',
    cursor: 'pointer',
  },
  pageBtnActive: {
    background: 'var(--color-primary)',
    borderColor: 'var(--color-primary)',
    color: '#fff',
  },
  pageInfo: { fontSize: '11px', color: 'var(--color-text-muted)', marginLeft: '8px' },
  mapPanel: {
    width: '380px',
    flexShrink: 0,
    borderLeft: '1px solid var(--color-border)',
    position: 'relative',
  },
}

const drawerStyles: Record<string, React.CSSProperties> = {
  overlay: {
    position: 'fixed',
    top: 0,
    right: 0,
    bottom: 0,
    background: 'transparent',
    zIndex: 100,
    display: 'flex',
    justifyContent: 'flex-end',
  },
  drawer: {
    width: '420px',
    height: '100%',
    background: 'var(--color-surface)',
    borderLeft: '1px solid var(--color-border)',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '16px 20px',
    borderBottom: '1px solid var(--color-border)',
    flexShrink: 0,
  },
  title: { fontSize: '15px', fontWeight: 600 },
  closeBtn: {
    background: 'transparent',
    border: 'none',
    color: 'var(--color-text-muted)',
    fontSize: '16px',
    cursor: 'pointer',
  },
  body: {
    overflowY: 'auto',
    padding: '16px 20px',
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
  },
  address: { fontSize: '15px', fontWeight: 600, lineHeight: 1.5 },
  section: { display: 'flex', flexDirection: 'column', gap: '4px' },
  sectionTitle: {
    fontSize: '10px',
    fontWeight: 700,
    color: 'var(--color-text-muted)',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    marginBottom: '4px',
    borderBottom: '1px solid var(--color-border)',
    paddingBottom: '4px',
  },
  row: { display: 'flex', justifyContent: 'space-between', padding: '3px 0' },
  rowLabel: { color: 'var(--color-text-muted)', fontSize: '12px' },
  rowValue: { fontSize: '12px', fontWeight: 500, textAlign: 'right', maxWidth: '220px' },
  parcelId: { fontSize: '10px', color: 'var(--color-text-muted)', marginTop: '8px' },
  locateBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    background: 'transparent',
    border: '1px solid var(--color-border)',
    borderRadius: '6px',
    color: 'var(--color-primary)',
    padding: '6px 12px',
    fontSize: '12px',
    fontWeight: 600,
    marginBottom: '4px',
    cursor: 'pointer',
  },
}

const saveModalStyles: Record<string, React.CSSProperties> = {
  overlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.6)',
    zIndex: 200,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  modal: {
    background: 'var(--color-surface)',
    border: '1px solid var(--color-border)',
    borderRadius: '12px',
    padding: '28px',
    width: '380px',
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
  },
  title: { fontSize: '16px', fontWeight: 700 },
  label: { display: 'flex', flexDirection: 'column', gap: '6px' },
  labelText: { fontSize: '12px', color: 'var(--color-text-muted)' },
  input: {
    background: 'var(--color-bg)',
    border: '1px solid var(--color-border)',
    borderRadius: '6px',
    padding: '9px 12px',
    color: 'var(--color-text)',
    fontSize: '13px',
    outline: 'none',
  },
  actions: { display: 'flex', justifyContent: 'flex-end', gap: '10px' },
  cancelBtn: {
    background: 'transparent',
    border: '1px solid var(--color-border)',
    borderRadius: '6px',
    color: 'var(--color-text)',
    padding: '8px 16px',
    fontSize: '13px',
    cursor: 'pointer',
  },
  saveBtn: {
    background: 'var(--color-primary)',
    border: 'none',
    borderRadius: '6px',
    color: '#fff',
    padding: '8px 16px',
    fontSize: '13px',
    fontWeight: 600,
    cursor: 'pointer',
  },
}
