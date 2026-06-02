import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import AppNav from '../components/AppNav'
import { getProperty } from '../api/properties'
import { getMe } from '../api/auth'
import type { PropertyDetail, SaleHistoryEntry } from '../types/api'
import Map, { Marker, Popup } from 'react-map-gl/maplibre'
import 'maplibre-gl/dist/maplibre-gl.css'

function fmt(n: number | null | undefined, prefix = ''): string {
  if (n == null) return '—'
  return prefix + n.toLocaleString()
}

function fmtFloat(n: number | null | undefined, decimals = 2): string {
  if (n == null) return '—'
  return n.toFixed(decimals)
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={s.section}>
      <div style={s.sectionTitle}>{title}</div>
      {children}
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={s.row}>
      <span style={s.rowLabel}>{label}</span>
      <span style={s.rowValue}>{value ?? '—'}</span>
    </div>
  )
}

export default function PropertyDetailPage() {
  const { countyFips, parcelId } = useParams<{ countyFips: string; parcelId: string }>()
  const navigate = useNavigate()

  const [detail, setDetail] = useState<PropertyDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [userName, setUserName] = useState<string | undefined>(undefined)

  useEffect(() => {
    getMe().then((u) => setUserName(u.full_name ?? u.email)).catch(() => undefined)
  }, [])

  useEffect(() => {
    if (!countyFips || !parcelId) return
    setDetail(null)
    setError(null)
    getProperty(countyFips, parcelId)
      .then(setDetail)
      .catch(() => setError('Property not found or access denied.'))
  }, [countyFips, parcelId])

  if (error) return (
    <div style={s.outer}>
      <AppNav userName={userName} />
      <div style={s.centerMsg}>{error}</div>
    </div>
  )

  if (!detail) return (
    <div style={s.outer}>
      <AppNav userName={userName} />
      <div style={s.centerMsg}>Loading…</div>
    </div>
  )

  return (
    <div style={s.outer}>
      <AppNav userName={userName} />
      <div style={s.subHeader}>
        <button style={s.backBtn} onClick={() => navigate(-1)}>← Back</button>
        <span style={s.parcelId}>Parcel {detail.parcel_id} · {detail.county_fips}</span>
      </div>
      <div style={s.body}>
        <h1 style={s.address}>
          {detail.phy_addr1 ?? '—'}<br />
          <span style={s.addressSub}>{detail.phy_city ?? '—'}, FL {detail.phy_zipcd ?? '—'}</span>
        </h1>

        <div style={s.grid}>
          <Section title="Ownership">
            <Row label="Owner" value={detail.own_name} />
            <Row label="Mailing" value={[detail.own_addr1, detail.own_city, detail.own_state, detail.own_zipcd].filter(Boolean).join(', ')} />
            <Row label="Absentee" value={detail.absentee_owner == null ? '—' : detail.absentee_owner ? 'Yes' : 'No'} />
          </Section>

          <Section title="Valuation">
            <Row label="Just Value" value={fmt(detail.jv, '$')} />
            <Row label="Assessed Value" value={fmt(detail.av_nsd, '$')} />
            <Row label="Land Value" value={fmt(detail.lnd_val, '$')} />
            <Row label="JV / sqft" value={detail.jv_per_sqft != null ? `$${fmtFloat(detail.jv_per_sqft)}` : '—'} />
            <Row label="ARV Estimate" value={fmt(detail.arv_estimate, '$')} />
            <Row label="ARV Spread" value={fmt(detail.arv_spread, '$')} />
            <Row label="ARV Source" value={detail.latest_listing?.arv_source ?? detail.arv_source ?? '—'} />
          </Section>

          <Section title="Property">
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
          </Section>

          <Section title="CAMA">
            <Row label="Quality Code" value={detail.cama_quality_code} />
            <Row label="Condition Code" value={detail.cama_condition_code} />
            <Row label="Foundation" value={detail.foundation_type} />
            <Row label="Exterior Wall" value={detail.exterior_wall} />
            <Row label="Roof Type" value={detail.roof_type} />
            <Row label="CAMA Enriched" value={detail.cama_enriched_at ? new Date(detail.cama_enriched_at).toLocaleDateString() : 'Not enriched'} />
          </Section>

          <Section title="Ratios">
            <Row label="Imp / Land Ratio" value={detail.improvement_to_land_ratio != null ? fmtFloat(detail.improvement_to_land_ratio, 4) : '—'} />
            <Row label="SOH Compression" value={detail.soh_compression_ratio != null ? fmtFloat(detail.soh_compression_ratio, 4) : '—'} />
            <Row label="Years Since Sale" value={detail.years_since_last_sale} />
          </Section>

          {detail.latest_listing && (
            <Section title="Latest Signal">
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
            </Section>
          )}
        </div>
    {detail.latitude != null && detail.longitude != null && (
        <div style={s.mapWrap}>
            <Map
            initialViewState={{
                longitude: detail.longitude,
                latitude: detail.latitude,
                zoom: 15,
            }}
            style={{ width: '100%', height: '100%' }}
            mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
            >
            <Marker longitude={detail.longitude} latitude={detail.latitude} />
            <Popup
                longitude={detail.longitude}
                latitude={detail.latitude}
                anchor="bottom"
                closeButton={false}
                closeOnClick={false}
                offset={20}
            >
                <div style={{ color: '#000', fontSize: '12px', lineHeight: 1.5 }}>
                <strong>{detail.phy_addr1}</strong><br />
                JV: {fmt(detail.jv, '$')}<br />
                ARV: {fmt(detail.arv_estimate, '$')}
                </div>
            </Popup>
            </Map>
        </div>
        )}      
        <Section title="Sale History">
          {detail.sale_history.length === 0 ? (
            <Row label="No sale history" value="—" />
          ) : (
            <table style={s.saleTable}>
              <thead>
                <tr>
                  {['Date','Price','Instrument','Qual','Type','Grantor','Grantee','$/sqft','Source'].map((h) => (
                    <th key={h} style={s.saleTh}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {detail.sale_history.map((sale: SaleHistoryEntry, i: number) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--color-border)' }}>
                    <td style={s.saleTd}>{sale.sale_date ?? '—'}</td>
                    <td style={s.saleTd}>{sale.sale_price != null ? fmt(sale.sale_price, '$') : '—'}</td>
                    <td style={s.saleTd}>{sale.instrument_type ?? '—'}</td>
                    <td style={s.saleTd}>{sale.qualification_code ?? '—'}</td>
                    <td style={s.saleTd}>{sale.sale_type ?? '—'}</td>
                    <td style={s.saleTd}>{sale.grantor || '—'}</td>
                    <td style={s.saleTd}>{sale.grantee || '—'}</td>
                    <td style={s.saleTd}>{sale.price_per_sqft != null ? `$${sale.price_per_sqft.toFixed(2)}` : '—'}</td>
                    <td style={s.saleTd}>{sale.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Section>
      </div>
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  outer: { minHeight: '100vh', background: 'var(--color-bg)', display: 'flex', flexDirection: 'column' },
  subHeader: {
    display: 'flex', alignItems: 'center', gap: '16px',
    padding: '0 32px', height: '44px',
    background: 'var(--color-surface)', borderBottom: '1px solid var(--color-border)',
    flexShrink: 0,
  },
  backBtn: {
    background: 'transparent', border: 'none',
    color: 'var(--color-primary)', fontSize: '13px', cursor: 'pointer', padding: '4px 0',
  },
  parcelId: { fontSize: '12px', color: 'var(--color-text-muted)' },
  body: { padding: '32px', maxWidth: '960px', margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: '24px' },
  address: { fontSize: '22px', fontWeight: 700, lineHeight: 1.4, margin: 0 },
  addressSub: { fontSize: '16px', fontWeight: 400, color: 'var(--color-text-muted)' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '16px' },
  section: { background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: '10px', padding: '16px', display: 'flex', flexDirection: 'column', gap: '4px' },
  sectionTitle: { fontSize: '10px', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.08em', marginBottom: '8px', borderBottom: '1px solid var(--color-border)', paddingBottom: '4px' },
  row: { display: 'flex', justifyContent: 'space-between', padding: '3px 0' },
  rowLabel: { color: 'var(--color-text-muted)', fontSize: '12px' },
  rowValue: { fontSize: '12px', fontWeight: 500, textAlign: 'right' as const, maxWidth: '200px' },
  saleTable: { width: '100%', borderCollapse: 'collapse' as const, fontSize: '12px' },
  saleTh: { padding: '8px 10px', textAlign: 'left' as const, fontWeight: 600, color: 'var(--color-text-muted)', borderBottom: '1px solid var(--color-border)', background: 'var(--color-surface)', whiteSpace: 'nowrap' as const },
  saleTd: { padding: '8px 10px', verticalAlign: 'middle' as const },
  centerMsg: { padding: '60px', textAlign: 'center' as const, color: 'var(--color-text-muted)' },
  mapWrap: {
    width: '100%',
    height: '400px',
    borderRadius: '10px',
    overflow: 'hidden',
    border: '1px solid var(--color-border)',
  },
}
