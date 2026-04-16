import { useEffect, useState } from 'react'
import { api, Chat, User } from '../services/api'

export function NewChatModal({ onClose, onCreated }: { onClose: () => void; onCreated: (c: Chat) => void }) {
  const [users, setUsers] = useState<User[]>([])
  const [search, setSearch] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.listUsers().then(setUsers).catch(() => {}) }, [])

  const filtered = users.filter(u => {
    if (!search) return true
    const q = search.toLowerCase()
    return u.username.toLowerCase().includes(q) || u.display_name.toLowerCase().includes(q)
  })

  async function pick(u: User) {
    if (busy) return
    setBusy(true)
    try {
      const chat = await api.openPersonal(u.username)
      onCreated(chat)
    } catch (e: any) {
      alert(e.message || e)
      setBusy(false)
    }
  }

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="head">
          <h2>$ NEW CHAT</h2>
          <button className="close" onClick={onClose}>×</button>
        </div>
        <div className="body">
          <div className="search-line">
            <input autoFocus placeholder="search users..." value={search} onChange={e => setSearch(e.target.value)} />
          </div>
          {filtered.length === 0 && <div className="empty-pad">no users</div>}
          {filtered.map(u => (
            <div key={u.id} className="user-row" onClick={() => pick(u)}>
              <div>
                <div className="uname">{u.username}</div>
                <div className="udisp">{u.display_name}</div>
              </div>
              {u.is_online && <div className="online-dot" />}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export function NewGroupModal({ onClose, onCreated }: { onClose: () => void; onCreated: (c: Chat) => void }) {
  const [users, setUsers] = useState<User[]>([])
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')
  const [name, setName] = useState('')
  const [step, setStep] = useState<'pick' | 'name'>('pick')
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.listUsers().then(setUsers).catch(() => {}) }, [])

  const filtered = users.filter(u => {
    if (!search) return true
    const q = search.toLowerCase()
    return u.username.toLowerCase().includes(q) || u.display_name.toLowerCase().includes(q)
  })

  function toggle(u: string) {
    const s = new Set(picked)
    if (s.has(u)) s.delete(u); else s.add(u)
    setPicked(s)
  }

  async function create() {
    if (!name.trim() || picked.size === 0 || busy) return
    setBusy(true)
    try {
      const chat = await api.createGroup(name.trim(), Array.from(picked))
      onCreated(chat)
    } catch (e: any) {
      alert(e.message || e)
      setBusy(false)
    }
  }

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="head">
          <h2>{step === 'pick' ? '$ ADD MEMBERS' : '$ GROUP NAME'}</h2>
          <button className="close" onClick={onClose}>×</button>
        </div>
        <div className="body">
          {step === 'pick' ? (
            <>
              <div className="search-line">
                <input autoFocus placeholder="search users..." value={search} onChange={e => setSearch(e.target.value)} />
              </div>
              {filtered.length === 0 && <div className="empty-pad">no users</div>}
              {filtered.map(u => {
                const sel = picked.has(u.username)
                return (
                  <div key={u.id} className={'user-row' + (sel ? ' sel' : '')} onClick={() => toggle(u.username)}>
                    <div>
                      <div className="uname">{u.username}</div>
                      <div className="udisp">{u.display_name}</div>
                    </div>
                    <div className={'check' + (sel ? ' on' : '')}>{sel ? '✓' : ''}</div>
                  </div>
                )
              })}
            </>
          ) : (
            <div className="field-wrap">
              <div className="field" style={{ marginBottom: 4 }}>
                <label>group name</label>
                <input autoFocus value={name} onChange={e => setName(e.target.value)} placeholder="my team" maxLength={100} />
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 12 }}>
                {picked.size + 1} members (including you):
              </div>
              <div style={{ fontSize: 11, color: 'var(--accent)', marginTop: 4 }}>
                {Array.from(picked).map(u => '@' + u).join(', ')}
              </div>
            </div>
          )}
        </div>
        <div className="foot">
          {step === 'pick' ? (
            <button className="primary" disabled={picked.size === 0} onClick={() => setStep('name')}>
              next ({picked.size}) →
            </button>
          ) : (
            <>
              <button onClick={() => setStep('pick')}>← back</button>
              <button className="primary" disabled={!name.trim() || busy} onClick={create}>
                {busy ? '...' : '$ create'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
