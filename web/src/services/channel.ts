// Real-time channel for one chat.
// First tries WebSocket (the global server one — listens for new_message
// events for ALL chats this user is in). If WebSocket fails to connect
// within 5 seconds, falls back to REST polling every 2 seconds.

import { api, config, Message } from './api'

type Mode = 'connecting' | 'ws' | 'polling' | 'failed'

export interface ChannelEvent {
  type: 'message' | 'status' | 'chat_created'
  message?: Message
  connected?: boolean
  mode?: Mode
  chat?: any
}

export class RealtimeChannel {
  private chatId: number
  private lastId: number
  private listeners = new Set<(e: ChannelEvent) => void>()

  private ws: WebSocket | null = null
  private wsRetryTimer: number | null = null
  private wsConnectTimeout: number | null = null

  private pollTimer: number | null = null
  private mode: Mode = 'connecting'
  private destroyed = false

  constructor(chatId: number, initialLastId: number) {
    this.chatId = chatId
    this.lastId = initialLastId
  }

  on(fn: (e: ChannelEvent) => void): () => void {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  private emit(e: ChannelEvent) {
    this.listeners.forEach(fn => {
      try { fn(e) } catch {}
    })
  }

  private setMode(mode: Mode) {
    this.mode = mode
    this.emit({ type: 'status', mode, connected: mode === 'ws' || mode === 'polling' })
  }

  start() {
    this.tryWebSocket()
  }

  /** Reset to a new chat id without recreating the channel. */
  switchChat(chatId: number, lastId: number) {
    this.chatId = chatId
    this.lastId = lastId
  }

  noteSentMessage(msg: Message) {
    if (msg.id > this.lastId) this.lastId = msg.id
  }

  destroy() {
    this.destroyed = true
    this.listeners.clear()
    if (this.wsRetryTimer) clearTimeout(this.wsRetryTimer)
    if (this.wsConnectTimeout) clearTimeout(this.wsConnectTimeout)
    if (this.pollTimer) clearTimeout(this.pollTimer)
    if (this.ws) {
      try { this.ws.close() } catch {}
      this.ws = null
    }
  }

  // --------------- WebSocket ---------------
  private tryWebSocket() {
    if (this.destroyed) return
    if (!config.token || !config.server) return

    const wsUrl = config.server.replace(/^http/, 'ws') + '/ws?token=' + encodeURIComponent(config.token)
    let ws: WebSocket
    try {
      ws = new WebSocket(wsUrl)
    } catch {
      this.fallbackToPolling()
      return
    }
    this.ws = ws

    // 5-second connect timeout — if WS doesn't open, switch to polling
    this.wsConnectTimeout = window.setTimeout(() => {
      if (ws.readyState !== WebSocket.OPEN) {
        try { ws.close() } catch {}
        this.fallbackToPolling()
      }
    }, 5000)

    ws.onopen = () => {
      if (this.wsConnectTimeout) clearTimeout(this.wsConnectTimeout)
      this.setMode('ws')
    }

    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data)
        if (data.type === 'new_message' && data.message) {
          const msg = data.message as Message
          if (msg.id > this.lastId) this.lastId = msg.id
          this.emit({ type: 'message', message: msg })
        } else if (data.type === 'chat_created' && data.chat) {
          this.emit({ type: 'chat_created', chat: data.chat })
        }
      } catch {}
    }

    ws.onclose = () => {
      if (this.destroyed) return
      this.ws = null
      // If we were connected and got disconnected — try WS again.
      // If we never connected, polling fallback already kicked in.
      if (this.mode === 'ws') {
        this.setMode('connecting')
        this.wsRetryTimer = window.setTimeout(() => this.tryWebSocket(), 3000)
      }
    }

    ws.onerror = () => {
      try { ws.close() } catch {}
    }
  }

  // --------------- Polling ---------------
  private fallbackToPolling() {
    if (this.destroyed) return
    if (this.mode === 'polling') return
    this.setMode('polling')
    this.pollLoop()
  }

  private async pollLoop() {
    if (this.destroyed || this.mode !== 'polling') return
    try {
      const newMsgs = await api.getMessagesSince(this.chatId, this.lastId)
      for (const msg of newMsgs) {
        if (msg.id > this.lastId) this.lastId = msg.id
        this.emit({ type: 'message', message: msg })
      }
      // signal connected after any successful poll
      if (this.mode === 'polling') {
        this.emit({ type: 'status', mode: 'polling', connected: true })
      }
    } catch {
      this.emit({ type: 'status', mode: 'polling', connected: false })
    }
    this.pollTimer = window.setTimeout(() => this.pollLoop(), 2000)
  }
}
