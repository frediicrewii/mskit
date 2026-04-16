import { useEffect, useRef, useState, KeyboardEvent } from 'react'
import { api, Chat, Message, User } from '../services/api'
import { RealtimeChannel } from '../services/channel'
import { fmtTime, linkify, userColor } from '../services/utils'

interface Props {
  me: User
  chat: Chat | null
  channel: RealtimeChannel | null
}

const ASCII_LOGO = `
  ┌─────────────┐
  │  > tg       │
  │  > select   │
  │  > a chat   │
  └─────────────┘
`

export default function ChatView({ me, chat, channel }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [text, setText] = useState('')
  const [pending, setPending] = useState<{ url: string; name: string; type: string; preview?: string } | null>(null)
  const [uploading, setUploading] = useState(false)
  const [busy, setBusy] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  // Initial load on chat switch
  useEffect(() => {
    if (!chat) { setMessages([]); return }
    let cancelled = false
    api.getMessages(chat.id, 50).then(msgs => {
      if (cancelled) return
      setMessages(msgs)
      requestAnimationFrame(() => scrollToBottom())
    }).catch(() => {})
    return () => { cancelled = true }
  }, [chat?.id])

  // Subscribe to channel events
  useEffect(() => {
    if (!channel || !chat) return
    const off = channel.on(ev => {
      if (ev.type === 'message' && ev.message && ev.message.chat_id === chat.id) {
        setMessages(prev => {
          if (prev.some(m => m.id === ev.message!.id)) return prev
          return [...prev, ev.message!]
        })
        // schedule autoscroll if user is near bottom
        requestAnimationFrame(() => maybeScrollToBottom())
      }
    })
    return off
  }, [channel, chat?.id])

  function scrollToBottom() {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }

  function maybeScrollToBottom() {
    const el = scrollRef.current
    if (!el) return
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight
    if (dist < 200) scrollToBottom()
  }

  function autoresize() {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(140, ta.scrollHeight) + 'px'
  }

  async function send() {
    if (!chat || busy) return
    const trimmed = text.trim()
    if (!trimmed && !pending) return
    setBusy(true)
    try {
      const sent = await api.sendMessage(
        chat.id,
        trimmed || undefined,
        pending ? { file_url: pending.url, file_name: pending.name, file_type: pending.type } : undefined
      )
      // optimistic-ish: insert immediately so user doesn't wait for echo
      setMessages(prev => prev.some(m => m.id === sent.id) ? prev : [...prev, sent])
      channel?.noteSentMessage(sent)
      setText('')
      setPending(null)
      if (taRef.current) taRef.current.style.height = 'auto'
      requestAnimationFrame(() => scrollToBottom())
    } catch (e: any) {
      alert('send failed: ' + (e.message || e))
    } finally {
      setBusy(false)
    }
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  async function onFilePick(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (!f) return
    if (f.size > 50 * 1024 * 1024) {
      alert('max 50 MB')
      return
    }
    setUploading(true)
    try {
      const up = await api.uploadFile(f)
      const preview = up.file_type === 'image' ? URL.createObjectURL(f) : undefined
      setPending({ url: up.file_url, name: up.file_name, type: up.file_type, preview })
    } catch (e: any) {
      alert('upload failed: ' + (e.message || e))
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  if (!chat) {
    return (
      <main className="chat">
        <div className="chat-empty">
          <div className="ascii">{ASCII_LOGO}</div>
          <div className="hint">no chat selected</div>
        </div>
      </main>
    )
  }

  const isGroup = chat.is_group
  const other = !isGroup ? chat.members.find(m => m.id !== me.id) : null
  const title = isGroup ? (chat.name || 'group') : (other?.username || '?')
  const subline = isGroup
    ? `${chat.members.length} members`
    : (other?.is_online ? 'online' : 'offline')

  return (
    <main className="chat">
      <header className="chat-head">
        <div className="title">
          <span className={'marker' + (isGroup ? '' : ' dm')}>{isGroup ? '#' : '@'}</span>
          {title}
        </div>
        <div className={'meta' + (other?.is_online ? ' online' : '')}>{subline}</div>
      </header>

      <div className="messages" ref={scrollRef}>
        {messages.length === 0 ? (
          <div className="msg-system">— no messages yet —</div>
        ) : messages.map(m => {
          const isMe = m.sender_id === me.id
          const whoClass = isMe ? 'who me' : (isGroup ? 'who other' : 'who them')
          const whoStyle = !isMe && isGroup ? { color: userColor(m.sender_username) } : undefined
          const whoLabel = isMe ? 'you' : m.sender_username
          return (
            <div key={m.id} className="msg-line">
              <div className="time">{fmtTime(m.created_at)}</div>
              <div className={whoClass} style={whoStyle}>{whoLabel}:</div>
              <div className="body">
                {m.content && <span>{linkifiedNodes(m.content)}</span>}
                {m.file_type === 'image' && m.file_url && (
                  <a href={api.resolveFileUrl(m.file_url)} target="_blank" rel="noopener noreferrer">
                    <img className="img-preview" src={api.resolveFileUrl(m.file_url)} alt={m.file_name || ''} />
                  </a>
                )}
                {m.file_type === 'file' && m.file_url && (
                  <div>
                    <a className="file-pill" href={api.resolveFileUrl(m.file_url)} download={m.file_name || ''}>
                      <span>[file]</span>
                      <span>{m.file_name || 'download'}</span>
                    </a>
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {pending && (
        <div className="attach-pill">
          {pending.preview && <img src={pending.preview} alt="" />}
          <span>{pending.type === 'image' ? '[image]' : '[file]'}</span>
          <span className="name">{pending.name}</span>
          <button onClick={() => setPending(null)}>× cancel</button>
        </div>
      )}

      <div className="composer">
        <span className="prompt">$</span>
        <textarea
          ref={taRef}
          rows={1}
          value={text}
          onChange={e => { setText(e.target.value); autoresize() }}
          onKeyDown={onKey}
          placeholder={uploading ? 'uploading...' : 'type message, ↵ send, ⇧↵ newline'}
          disabled={uploading}
        />
        <input ref={fileRef} type="file" style={{ display: 'none' }} onChange={onFilePick} />
        <div className="composer-actions">
          <button className="icon-btn" onClick={() => fileRef.current?.click()} disabled={uploading} title="Attach file">⎘</button>
          <button className="icon-btn" onClick={send} disabled={busy || (!text.trim() && !pending)} title="Send">↵</button>
        </div>
      </div>
    </main>
  )
}

function linkifiedNodes(text: string) {
  return linkify(text).map((part, i) => {
    if (typeof part === 'string') return <span key={i}>{part}</span>
    return <a key={i} href={part.url} target="_blank" rel="noopener noreferrer">{part.url}</a>
  })
}
