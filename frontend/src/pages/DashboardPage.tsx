import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppNav from '../components/AppNav'
import { getMe } from '../api/auth'
import { getDashboard } from '../api/dashboard'
import { toggleFavorite } from '../api/profiles'
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

  function handleRunProfile(entry: ProfileActivityEntry) {
    navigate('/results', {
      state: {
        profileId: entry.profile_id,
        countyFips: entry.county_fips,
        filterState: null,
      },
    })
  }

  function handleEditProfile(entry: ProfileActivityEntry) {
    navigate('/search', {
      state: {
        profileId: entry.profile_id,
        countyFips: entry.county_fips,
      },
    })
  }

  async function handleToggleFavorite(entry: ProfileActivityEntry) {
    try {
      const res = await toggleFavorite(entry.profile_id)
      setDashboard((prev: DashboardResponse | null) => {
        if (!prev) return prev
        return {
          ...prev,
          profile_activity: prev.profile_activity.map((e) =>
            e.profile_id === entry.profile_id
              ? { ...e, is_favorite: res.is_favorite }
              : e
          ),
        }
      })
    } catch {
      // silent — star reverts visually on next load
    }
  }

  if (loadError) return <div style={s.centerMsg}>{loadError}</div>
  if (!user || !dashboard) return <div style={s.centerMsg}>Loading…</div>

  const { profile_activity, outreach_pipeline } = dashboard

  return (
    <div style={s.outer}>
      <AppNav userName={user.full_name ?? user.email} />

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
            <button style={s.primaryBtn} onClick={() => navigate('/search')}>
              + New Search
            </button>
          </div>

          {profile_activity.length === 0 ? (
            <div style={s.emptyState}>
              <p style={s.emptyText}>No profiles run yet.</p>
              <button style={s.primaryBtn} onClick={() => navigate('/search')}>
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
                  onEdit={() => handleEditProfile(entry)}
                  onToggleFavorite={() => handleToggleFavorite(entry)}
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
  entry, onRun, onEdit, onToggleFavorite,
}: {
  entry: ProfileActivityEntry
  onRun: () => void
  onEdit: () => void
  onToggleFavorite: () => void
}) {
  return (
    <div style={s.profileRow}>
      <div style={s.profileLeft}>
        <span
          style={{ ...s.favStar, cursor: 'pointer' }}
          title={entry.is_favorite ? 'Remove from favorites' : 'Add to favorites'}
          onClick={onToggleFavorite}
        >
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
      <div style={s.rowActions}>
        <button style={s.editBtn} onClick={onEdit}>Edit</button>
        <button style={s.runBtn} onClick={onRun}>Run</button>
      </div>
    </div>
  )
}

// ── Styles ────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  outer: {
    minHeight: '100vh',
    background: 'var(--color-bg)',
    display: 'flex',
    flexDirection: 'column',
  },
  body: {
    padding: '32px',
    maxWidth: '960px',
    margin: '0 auto',
    width: '100%',
    display: 'flex',
    flexDirection: 'column',
    gap: '40px',
  },
  section: {},
  sectionHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '16px',
  },
  sectionTitle: {
    fontSize: '13px',
    fontWeight: 600,
    color: 'var(--color-text-muted)',
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    margin: 0,
  },
  primaryBtn: {
    background: 'var(--color-primary)',
    border: 'none',
    borderRadius: '6px',
    color: '#fff',
    padding: '8px 16px',
    fontWeight: 600,
    fontSize: '13px',
    cursor: 'pointer',
  },
  pipelineRow: { display: 'flex', gap: '12px', flexWrap: 'wrap' },
  pipelineTile: {
    background: 'var(--color-surface)',
    border: '1px solid var(--color-border)',
    borderRadius: '10px',
    padding: '16px 24px',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
    minWidth: '160px',
  },
  pipelineValue: { fontSize: '28px', fontWeight: 700 },
  pipelineValueMuted: { color: 'var(--color-text-muted)' },
  pipelineLabel: { fontSize: '12px', color: 'var(--color-text-muted)' },
  pipelineMutedNote: {
    fontSize: '10px',
    color: 'var(--color-text-muted)',
    fontStyle: 'italic',
  },
  profileList: {
    display: 'flex',
    flexDirection: 'column',
    border: '1px solid var(--color-border)',
    borderRadius: '10px',
    overflow: 'hidden',
  },
  profileRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '14px 20px',
    background: 'var(--color-surface)',
    borderBottom: '1px solid var(--color-border)',
  },
  profileLeft: { display: 'flex', alignItems: 'center', gap: '14px' },
  favStar: {
    fontSize: '18px',
    color: 'var(--color-warning)',
    userSelect: 'none',
  },
  profileInfo: { display: 'flex', flexDirection: 'column', gap: '3px' },
  profileName: {
    fontSize: '14px',
    fontWeight: 600,
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  systemBadge: {
    fontSize: '10px',
    background: 'var(--color-border)',
    color: 'var(--color-text-muted)',
    borderRadius: '4px',
    padding: '1px 6px',
    fontWeight: 500,
  },
  profileMeta: { fontSize: '12px', color: 'var(--color-text-muted)' },
  rowActions: { display: 'flex', gap: '8px', alignItems: 'center' },
  editBtn: {
    background: 'transparent',
    border: '1px solid var(--color-border)',
    borderRadius: '6px',
    color: 'var(--color-text)',
    padding: '7px 18px',
    fontWeight: 600,
    fontSize: '13px',
    cursor: 'pointer',
  },
  runBtn: {
    background: 'var(--color-primary)',
    border: 'none',
    borderRadius: '6px',
    color: '#fff',
    padding: '7px 18px',
    fontWeight: 600,
    fontSize: '13px',
    cursor: 'pointer',
  },
  emptyState: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '16px',
    padding: '48px 0',
  },
  emptyText: { color: 'var(--color-text-muted)', fontSize: '14px', margin: 0 },
  centerMsg: {
    padding: '40px',
    textAlign: 'center',
    color: 'var(--color-text-muted)',
  },
}
