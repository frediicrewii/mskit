import { useEffect, useRef, useState } from 'react'
import { api, Chat, Message, User, config } from './services/api'
import { RealtimeChannel } from './services/channel'
import AuthScreen from './components/AuthScreen'
import Sidebar from './components/Sidebar'
import ChatView from './components/ChatView'
import { NewChatModal, NewGroupModal } from './components/Modals'

export default function App() {
  const [me, setMe] = useState<User | null>(config.me)
  const [chats, setChats] = useState<Chat[]>([])
  const [active, setActive] = useState<Chat | null>(null)
  const [modal, setModal] = useState<'new' | 'group' | null>(null)
  const [connected, setConnected] = useState(false)
  const [mode, setMode] = useState<string>('connecting')
  const channelRef = useRef<RealtimeChannel | null>(null)

  // verify token & load chats
  useEffect(() => {
    if (!me) return
    api.me().then(u => {
      setMe(u)
      config.me = u
    }).catch(() => {
      // token invalid — log out
      config.clear()
      setMe(null)
    })
    refreshChats()
  }, [me?.id])

  function refreshChats() {
    api.listChats().then(setChats).catch(() => {})
  }

  // Manage realtime channel — global one for the user, switching chat id when active changes
  useEffect(() => {
    if (!me || !active) {
      if (channelRef.current) {
        channelRef.current.destroy()
        channelRef.current = null
        setConnected(false)
      }
      return
    }

    if (!channelRef.current) {
      const initial = 0
      channelRef.current = new RealtimeChannel(active.id, initial)
      channelRef.current.on(ev => {
        if (ev.type === 'status') {
          setConnected(!!ev.connected)
          if (ev.mode) setMode(ev.mode)
        } else if (ev.type === 'message' && ev.message) {
          // bump chat in sidebar even if it's not the active one
          updateLastMessageInChat(ev.message)
        } else if (ev.type === 'chat_created' && ev.chat) {
          setChats(prev => prev.some(c => c.id === ev.chat!.id) ? prev : [ev.chat, ...prev])
        }
      })
      channelRef.current.start()
    } else {
      channelRef.current.switchChat(active.id, 0)
    }
  }, [me?.id, active?.id])

  // also fetch initial last_id for active chat to seed the channel
  useEffect(() => {
    if (!active || !channelRef.current) return
    api.getMessages(active.id, 1).then(msgs => {
      const lastId = msgs.length ? msgs[msgs.length - 1].id : 0
      channelRef.current?.switchChat(active.id, lastId)
    }).catch(() => {})
  }, [active?.id])

  function updateLastMessageInChat(msg: Message) {
    setChats(prev => {
      const updated = prev.map(c => {
        if (c.id !== msg.chat_id) return c
        return {
          ...c,
          last_message: {
            id: msg.id,
            content: msg.content,
            file_type: msg.file_type,
            file_name: msg.file_name,
            sender_id: msg.sender_id,
            sender_username: msg.sender_username,
            created_at: msg.created_at,
          },
        }
      })
      updated.sort((a, b) => {
        const ta = a.last_message?.created_at || ''
        const tb = b.last_message?.created_at || ''
        return tb.localeCompare(ta)
      })
      return updated
    })
  }

  function handleAuth(user: User) {
    setMe(user)
  }

  function handleLogout() {
    if (channelRef.current) {
      channelRef.current.destroy()
      channelRef.current = null
    }
    config.clear()
    setMe(null)
    setChats([])
    setActive(null)
  }

  function handleChatCreated(chat: Chat) {
    setChats(prev => prev.some(c => c.id === chat.id) ? prev : [chat, ...prev])
    setActive(chat)
    setModal(null)
  }

  if (!me) return <AuthScreen onAuth={handleAuth} />

  return (
    <>
      {!connected && (
        <div className="banner">○ DISCONNECTED — RECONNECTING</div>
      )}
      <div className="app" style={{ height: connected ? '100vh' : 'calc(100vh - 22px)' }}>
        <Sidebar
          me={me}
          chats={chats}
          activeId={active?.id ?? null}
          connected={connected}
          mode={mode}
          onSelect={setActive}
          onNew={() => setModal('new')}
          onNewGroup={() => setModal('group')}
          onLogout={handleLogout}
        />
        <ChatView me={me} chat={active} channel={channelRef.current} />
        {modal === 'new' && <NewChatModal onClose={() => setModal(null)} onCreated={handleChatCreated} />}
        {modal === 'group' && <NewGroupModal onClose={() => setModal(null)} onCreated={handleChatCreated} />}
      </div>
    </>
  )
}
