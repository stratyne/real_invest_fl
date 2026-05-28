import { useNavigate } from 'react-router-dom'

interface AppNavProps {
  userName?: string
}

export default function AppNav({ userName }: AppNavProps) {
  const navigate = useNavigate()

  function handleSignOut() {
    localStorage.removeItem('access_token')
    navigate('/login')
  }

  return (
    <nav style={s.nav}>
      <div style={s.left}>
        <span
          style={s.brand}
          onClick={() => navigate('/dashboard')}
          title="Go to Dashboard"
        >
          Penstock
        </span>
        <button style={s.navLink} onClick={() => navigate('/dashboard')}>
          Dashboard
        </button>
        <button style={s.navLink} onClick={() => navigate('/search')}>
          New Search
        </button>
      </div>
      <div style={s.right}>
        {userName && <span style={s.userName}>{userName}</span>}
        <button style={s.signOutBtn} onClick={handleSignOut}>
          Sign Out
        </button>
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
}
