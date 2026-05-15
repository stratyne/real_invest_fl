import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getMe } from '../api/auth'
import { getDashboard } from '../api/dashboard'
import type { UserProfile, DashboardResponse, ProfileActivityEntry } from '../types/api'

export default function DashboardPage() {
  const navigate = useNavigate()

  const [user, setUser] = useState<UserProfile | null>(null)
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([getMe(), getDashboard()])
      .then(([u, d]) => { setUser(u); setDashboard(d) })
      .catch(() => setLoadError('Failed to load dashboard.'))
  }, [])

  function handleSignOut() {
    localStorage.removeItem('access_token')
    navigate('/login')
  }

  function handleRunProfile(entry: ProfileActivityEntry) {
    navigate('/search', { state: { profileId: entry.profile_id, countyFips: entry.county_fips } })
  }

  function handleNewSearch() {
    navigate('/search')
  }

  if (loadError) return <div style={s.centerMsg}>{loadError}</div>
  if (!user || !dashboard) return <div style={s.centerMsg}>Loading…</div>

  const { profile_activity, outreach_pipeline } = dashboard

  return (
    <div style={s.outer}>

      {/* ── Header ── */}
      <header style={s.header}>
        <span style={s.brand}>Penstock</span>
        <div style={s.headerRight}>
          <span style={s.userName}>{user.full_name ?? user.email}</span>
          <button style={s.ghostBtn} onClick={handleNewSearch}>New Search</button>
          <button style={s.ghostBtn} onClick={handleSignOut}>Sign out</button>
        </div>
      </header>

      <div style={s.body}>

        {/* ── Outreach pipeline ── */}
        <section style={s.section}>
          <h2 style={s.sectionTitle}>Outreach Pipeline</h2>
          <div style={s.pipelineRow}>
            <PipelineTile label="Drafts Pending" value={outreach_pipeline.drafts_pending} />
            <PipelineTile label="Sent This Week" value={outreach_pipeline.sent_this_week} />
            <PipelineTile
              label="Responses Received"
              value={outreach_pipeline.responses_received}
              muted
            />
          </div>
        </section>

        {/* ── Profile activity ── */}
        <section style={s.section}>
          <div style={s.sectionHeader}>
            <h2 style={s.sectionTitle}>Filter Profiles</h2>
            <button style={s.primaryBtn} onClick={handleNewSearch}>
              + New Search
            </button>
          </div>

          {profile_activity.length === 0 ? (
            <div style={s.emptyState}>
              <p style={s.emptyText}>No profiles run yet.</p>
              <button style={s.primaryBtn} onClick={handleNewSearch}>
                Start your first search
              </button>
            </div>
          ) : (
            <div style={s.profileList}>
              {profile_activity.map((entry) => (
                <ProfileRow
                  key={entry.profile_id}
                  entry={entry}
                  onRun={() => handleRunProfile(entry)}
                />
              ))}
            </div>
          )}
        </section>

      </div>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────

function PipelineTile({
  label, value, muted = false,
}: {
  label: string
  value: number
  muted?: boolean
}) {
  return (
    <div style={s.pipelineTile}>
      <span style={{ ...s.pipelineValue, ...(muted ? s.pipelineValueMuted : {}) }}>
        {value}
      </span>
      <span style={s.pipelineLabel}>{label}</span>
      {muted && <span style={s.pipelineMutedNote}>inbound webhook — Phase 4 tail</span>}
    </div>
  )
}

function ProfileRow({
  entry, onRun,
}: {
  entry: ProfileActivityEntry
  onRun: () => void
}) {
  return (
    <div style={s.profileRow}>
      <div style={s.profileLeft}>
        <span style={s.favStar} title={entry.is_favorite ? 'Favorited' : 'Not favorited'}>
          {entry.is_favorite ? '★' : '☆'}
        </span>
        <div style={s.profileInfo}>
          <div style={s.profileName}>
            {entry.profile_name}
            {entry.is_system && <span style={s.systemBadge}>system</span>}
          </div>
          <div style={s.profileMeta}>
            {entry.county_fips.join(', ')}
            {entry.last_searched_at
              ? ` · Last run ${new Date(entry.last_searched_at).toLocaleDateString()}`
              : ' · Never run'}
            {entry.last_result_count != null && ` · ${entry.last_result_count.toLocaleString()} results`}
            {` · ${entry.run_count} run${entry.run_count !== 1 ? 's' : ''}`}
          </div>
        </div>
      </div>
      <button style={s.runBtn} onClick={onRun}>
        Run
      </button>
    </div>
  )
}

// ── Styles ────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  outer: { minHeight: '100vh', background: 'var(--color-bg)', display: 'flex', flexDirection: 'column' },
  header: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '0 32px', height: '56px', background: 'var(--color-surface)',
    borderBottom: '1px solid var(--color-border)', flexShrink: 0,
  },
  brand: { fontWeight: 700, fontSize: '18px' },
  headerRight: { display: 'flex', alignItems: 'center', gap: '12px' },
  userName: { color: 'var(--color-text-muted)', fontSize: '13px' },
  ghostBtn: {
    background: 'transparent', border: '1px solid var(--color-border)',
    borderRadius: '6px', color: 'var(--color-text-muted)', padding: '6px 12px', fontSize: '13px',
    cursor: 'pointer',
  },
  primaryBtn: {
    background: 'var(--color-primary)', border: 'none', borderRadius: '6px',
    color: '#fff', padding: '8px 16px', fontWeight: 600, fontSize: '13px', cursor: 'pointer',
  },
  body: { padding: '32px', maxWidth: '960px', margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: '40px' },
  section: {},
  sectionHeader: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' },
  sectionTitle: { fontSize: '13px', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', margin: 0 },
  pipelineRow: { display: 'flex', gap: '12px', flexWrap: 'wrap' },
  pipelineTile: {
    background: 'var(--color-surface)', border: '1px solid var(--color-border)',
    borderRadius: '10px', padding: '16px 24px', display: 'flex', flexDirection: 'column', gap: '4px',
    minWidth: '160px',
  },
  pipelineValue: { fontSize: '28px', fontWeight: 700 },
  pipelineValueMuted: { color: 'var(--color-text-muted)' },
  pipelineLabel: { fontSize: '12px', color: 'var(--color-text-muted)' },
  pipelineMutedNote: { fontSize: '10px', color: 'var(--color-text-muted)', fontStyle: 'italic' },
  profileList: {
    display: 'flex', flexDirection: 'column',
    border: '1px solid var(--color-border)', borderRadius: '10px', overflow: 'hidden',
  },
  profileRow: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '14px 20px', background: 'var(--color-surface)',
    borderBottom: '1px solid var(--color-border)',
  },
  profileLeft: { display: 'flex', alignItems: 'center', gap: '14px' },
  favStar: { fontSize: '18px', color: 'var(--color-warning)', cursor: 'default', userSelect: 'none' },
  profileInfo: { display: 'flex', flexDirection: 'column', gap: '3px' },
  profileName: { fontSize: '14px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' },
  systemBadge: {
    fontSize: '10px', background: 'var(--color-border)', color: 'var(--color-text-muted)',
    borderRadius: '4px', padding: '1px 6px', fontWeight: 500,
  },
  profileMeta: { fontSize: '12px', color: 'var(--color-text-muted)' },
  runBtn: {
    background: 'var(--color-primary)', border: 'none', borderRadius: '6px',
    color: '#fff', padding: '7px 18px', fontWeight: 600, fontSize: '13px', cursor: 'pointer',
  },
  emptyState: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px', padding: '48px 0' },
  emptyText: { color: 'var(--color-text-muted)', fontSize: '14px', margin: 0 },
  centerMsg: { padding: '40px', textAlign: 'center', color: 'var(--color-text-muted)' },
}
