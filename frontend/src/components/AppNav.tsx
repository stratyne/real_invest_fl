import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

interface AppNavProps {
  userName?: string
}

export default function AppNav({ userName }: AppNavProps) {
  const navigate = useNavigate()
  const [searchInput, setSearchInput] = useState('')
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)

  async function handleParcelSearch() {
    const pid = searchInput.trim().toUpperCase()
    if (!pid) return
    setSearching(true)
    setSearchError(null)
    try {
      const { lookupParcel } = await import('../api/properties')
      const results = await lookupParcel(pid)
      if (results.length === 0) {
        setSearchError('Not found')
      } else if (results.length === 1) {
        setSearchInput('')
        navigate(`/property/${results[0].county_fips}/${results[0].parcel_id}`)
      } else {
        setSearchInput('')
        navigate(`/property/${results[0].county_fips}/${results[0].parcel_id}`)
      }
    } catch {
      setSearchError('Lookup failed')
    } finally {
      setSearching(false)
    }
  }

  function handleSignOut() {
    localStorage.removeItem('access_token')
    navigate('/login')
  }

  return (
    <nav style={s.nav}>
      <div style={s.left}>
        <span style={s.brand} onClick={() => navigate('/dashboard')} title="Go to Dashboard">
          Penstock
        </span>
        <button style={s.navLink} onClick={() => navigate('/dashboard')}>Dashboard</button>
        <button style={s.navLink} onClick={() => navigate('/search')}>New Search</button>
        <div style={s.searchWrap}>
          <input
            style={s.searchInput}
            value={searchInput}
            onChange={(e) => { setSearchInput(e.target.value); setSearchError(null) }}
            onKeyDown={(e) => e.key === 'Enter' && handleParcelSearch()}
            placeholder="Parcel ID…"
            disabled={searching}
          />
          <button style={s.searchBtn} onClick={handleParcelSearch} disabled={searching || !searchInput.trim()}>
            {searching ? '…' : '↵'}
          </button>
          {searchError && <span style={s.searchError}>{searchError}</span>}
        </div>
      </div>
      <div style={s.right}>
        {userName && <span style={s.userName}>{userName}</span>}
        <button style={s.signOutBtn} onClick={handleSignOut}>Sign Out</button>
      </div>
    </nav>
  )
}

const s: Record<string, React.CSSProperties> = {
  nav: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 32px',
    height: '52px',
    background: 'var(--color-surface)',
    borderBottom: '1px solid var(--color-border)',
    flexShrink: 0,
    position: 'sticky',
    top: 0,
    zIndex: 50,
  },
  left: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  brand: {
    fontWeight: 700,
    fontSize: '16px',
    cursor: 'pointer',
    marginRight: '16px',
    userSelect: 'none',
  },
  navLink: {
    background: 'transparent',
    border: 'none',
    color: 'var(--color-text-muted)',
    fontSize: '13px',
    fontWeight: 500,
    padding: '6px 12px',
    borderRadius: '6px',
    cursor: 'pointer',
  },
  right: {
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
  },
  userName: {
    fontSize: '13px',
    color: 'var(--color-text-muted)',
  },
  signOutBtn: {
    background: 'transparent',
    border: '1px solid var(--color-border)',
    borderRadius: '6px',
    color: 'var(--color-text-muted)',
    padding: '5px 12px',
    fontSize: '13px',
    cursor: 'pointer',
  },
    searchWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    marginLeft: '8px',
    position: 'relative' as const,
  },
  searchInput: {
    background: 'var(--color-bg)',
    border: '1px solid var(--color-border)',
    borderRadius: '6px',
    color: 'var(--color-text)',
    padding: '5px 10px',
    fontSize: '12px',
    width: '180px',
    outline: 'none',
  },
  searchBtn: {
    background: 'transparent',
    border: '1px solid var(--color-border)',
    borderRadius: '6px',
    color: 'var(--color-text-muted)',
    padding: '5px 8px',
    fontSize: '12px',
    cursor: 'pointer',
  },
  searchError: {
    position: 'absolute' as const,
    top: '100%',
    left: 0,
    fontSize: '11px',
    color: 'var(--color-danger)',
    whiteSpace: 'nowrap' as const,
    paddingTop: '2px',
  },
}
