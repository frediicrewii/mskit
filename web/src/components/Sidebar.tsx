import { useMemo, useState } from 'react'
import { Chat, User } from '../services/api'
import { fmtTimeShort } from '../services/utils'

interface Props {
  me: User
  chats: Chat[]
  activeId: number | null
  connected: boolean
  mode: string
  onSelect: (chat: Chat) => void
  onNew: () => void
  onNewGroup: () => void
  onLogout: () => void
}

function chatTitle(c: Chat, meId: number): string {
  if (c.is_group) return c.name || 'group'
  const other = c.members.find(m => m.id !== meId)
  return other?.username || 'unknown'
}

function chatOnline(c: Chat, meId: number): boolean {
  if (c.is_group) return false
  const other = c.members.find(m => m.id !== meId)
  return other?.is_online ?? false
}

function chatPreview(c: Chat, meId: number): { from: string; text: string; isYou: boolean } | null {
  const lm = c.last_message
  if (!lm) return null
  const isYou = lm.sender_id === meId
  let text = lm.content || ''
  if (!text && lm.file_type === 'image') text = '[image]'
  else if (!text && lm.file_type) text = '[file: ' + (lm.file_name || '?') + ']'
  return {
    from: isYou ? 'you' : (c.is_group ? lm.sender_username : ''),
    text,
    isYou,
  }
}

export default function Sidebar(props: Props) {
  const { me, chats, activeId, connected, mode, onSelect, onNew, onNewGroup, onLogout } = props
  const [search, setSearch] = useState('')

  const filtered = useMemo(() => {
    if (!search) return chats
    const q = search.toLowerCase()
    return chats.filter(c => chatTitle(c, me.id).toLowerCase().includes(q))
  }, [chats, search, me.id])

  return (
    <aside className="sidebar">
      <div className="side-head">
        <div className="me">
          <span className="dot" />
          <span>@{me.username}</span>
        </div>
        <div className="actions">
          <button className="icon-btn" onClick={onNew} title="New chat">+</button>
          <button className="icon-btn" onClick={onNewGroup} title="New group">#</button>
          <button className="icon-btn" onClick={onLogout} title="Log out">×</button>
        </div>
      </div>

      <div className="search-row">
        <span>/</span>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="search..."
        />
      </div>

      <div className="chat-list">
        {filtered.length === 0 ? (
          <div className="empty-pad">
            {chats.length === 0 ? (
              <>
                no chats<br />
                <span className="blink">█</span> press <strong>+</strong> to start
              </>
            ) : 'no matches'}
          </div>
        ) : filtered.map(c => {
          const title = chatTitle(c, me.id)
          const preview = chatPreview(c, me.id)
          const online = chatOnline(c, me.id)
          const nameClass = c.is_group
            ? 'name group'
            : online ? 'name online-dm' : 'name dm'
          return (
            <div
              key={c.id}
              className={'chat-row' + (activeId === c.id ? ' active' : '')}
              onClick={() => onSelect(c)}
            >
              <div className="title-row">
                <div className={nameClass}>{title}</div>
                {c.last_message && (
                  <div className="when">{fmtTimeShort(c.last_message.created_at)}</div>
                )}
              </div>
              {preview && (
                <div className="preview">
                  {preview.isYou && <span className="you">you: </span>}
                  {!preview.isYou && preview.from && <span className="from">{preview.from}: </span>}
                  {preview.text || '...'}
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div className="side-foot">
        <span className={'conn' + (connected ? '' : ' off')}>
          {connected ? `● ${mode}` : '○ offline'}
        </span>
        <span>{chats.length} chat{chats.length !== 1 ? 's' : ''}</span>
      </div>
    </aside>
  )
}
