import { useState, FormEvent, useEffect } from 'react'
import { api, config, User } from '../services/api'

interface Props {
  onAuth: (user: User) => void
}

export default function AuthScreen({ onAuth }: Props) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [server, setServer] = useState(config.server || '')
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!config.server) {
      // Default: same-origin /api won't work for static deploys, leave blank
      // and let the user type their Render URL
    }
  }, [])

  async function submit(e: FormEvent) {
    e.preventDefault()
    setErr('')
    if (!server.trim()) {
      setErr('server URL required')
      return
    }
    config.server = server.trim()
    setLoading(true)
    try {
      const res = mode === 'login'
        ? await api.login(username.trim().toLowerCase(), password)
        : await api.register(username.trim().toLowerCase(), displayName.trim(), password)
      config.token = res.access_token
      config.me = res.user
      onAuth(res.user)
    } catch (e: any) {
      setErr(String(e.message || e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth">
      <form className="auth-box" onSubmit={submit}>
        <div className="prompt">
          <span>~/{mode} $</span>
          <span className="blink">█</span>
        </div>
        <h1>mskit</h1>
        <p className="sub">terminal-future messenger</p>

        <div className="server-row">
          <span>server:</span>
          <input
            type="url"
            value={server}
            onChange={e => setServer(e.target.value)}
            placeholder="https://your-server.onrender.com"
            required
          />
        </div>

        {err && <div className="error">! {err}</div>}

        <div className="field">
          <label>username</label>
          <input
            type="text"
            value={username}
            onChange={e => setUsername(e.target.value)}
            required minLength={3}
            autoFocus
            placeholder="alice"
          />
        </div>

        {mode === 'register' && (
          <div className="field">
            <label>display name (optional)</label>
            <input
              type="text"
              value={displayName}
              onChange={e => setDisplayName(e.target.value)}
              placeholder="Alice"
            />
          </div>
        )}

        <div className="field">
          <label>password</label>
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            required minLength={6}
            placeholder="••••••"
          />
        </div>

        <button className="btn" type="submit" disabled={loading}>
          {loading ? '...' : mode === 'login' ? '$ LOGIN' : '$ REGISTER'}
        </button>

        <div className="switch">
          {mode === 'login' ? "no account?" : "have account?"}
          <button type="button" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setErr('') }}>
            {mode === 'login' ? 'register' : 'login'}
          </button>
        </div>
      </form>
    </div>
  )
}
