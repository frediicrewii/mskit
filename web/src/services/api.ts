// Minimal REST client.

export interface User {
  id: number
  username: string
  display_name: string
  is_online: boolean
}

export interface Message {
  id: number
  chat_id: number
  sender_id: number
  sender_username: string
  sender_name: string
  content: string | null
  file_url: string | null
  file_name: string | null
  file_type: string | null
  created_at: string
}

export interface Chat {
  id: number
  is_group: boolean
  name: string | null
  members: User[]
  last_message: {
    id: number
    content: string | null
    file_type: string | null
    file_name: string | null
    sender_id: number
    sender_username: string
    created_at: string
  } | null
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: User
}

const STORAGE_SERVER = 'mskit.server'
const STORAGE_TOKEN = 'mskit.token'
const STORAGE_USER = 'mskit.user'

export const config = {
  get server(): string {
    return localStorage.getItem(STORAGE_SERVER) || ''
  },
  set server(v: string) {
    localStorage.setItem(STORAGE_SERVER, v.replace(/\/+$/, ''))
  },
  get token(): string | null {
    return localStorage.getItem(STORAGE_TOKEN)
  },
  set token(v: string | null) {
    if (v) localStorage.setItem(STORAGE_TOKEN, v)
    else localStorage.removeItem(STORAGE_TOKEN)
  },
  get me(): User | null {
    const raw = localStorage.getItem(STORAGE_USER)
    return raw ? JSON.parse(raw) : null
  },
  set me(v: User | null) {
    if (v) localStorage.setItem(STORAGE_USER, JSON.stringify(v))
    else localStorage.removeItem(STORAGE_USER)
  },
  clear() {
    localStorage.removeItem(STORAGE_TOKEN)
    localStorage.removeItem(STORAGE_USER)
  },
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!config.server) throw new Error('Server URL not configured')
  const token = config.token
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((init.headers as Record<string, string>) || {}),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(config.server + path, { ...init, headers })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const data = await res.json()
      detail = data.detail || detail
    } catch {}
    if (res.status === 401) {
      config.clear()
    }
    throw new Error(detail)
  }
  return res.json()
}

export const api = {
  register(username: string, display_name: string, password: string) {
    return request<AuthResponse>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, display_name: display_name || username, password }),
    })
  },
  login(username: string, password: string) {
    return request<AuthResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
  },
  me() {
    return request<User>('/api/auth/me')
  },
  listUsers() {
    return request<User[]>('/api/users/')
  },
  listChats() {
    return request<Chat[]>('/api/chats/')
  },
  openPersonal(username: string) {
    return request<Chat>('/api/chats/personal', {
      method: 'POST',
      body: JSON.stringify({ username }),
    })
  },
  createGroup(name: string, usernames: string[]) {
    return request<Chat>('/api/chats/group', {
      method: 'POST',
      body: JSON.stringify({ name, usernames }),
    })
  },
  getMessages(chat_id: number, limit = 50) {
    return request<Message[]>(`/api/messages/${chat_id}?limit=${limit}`)
  },
  getMessagesSince(chat_id: number, after_id: number) {
    return request<Message[]>(`/api/messages/${chat_id}/since/${after_id}`)
  },
  sendMessage(chat_id: number, content?: string, file?: {
    file_url: string
    file_name: string
    file_type: string
  }) {
    return request<Message>('/api/messages/', {
      method: 'POST',
      body: JSON.stringify({ chat_id, content, ...(file || {}) }),
    })
  },
  async uploadFile(file: File): Promise<{
    file_url: string
    file_name: string
    file_type: string
    size: number
  }> {
    const fd = new FormData()
    fd.append('file', file)
    const headers: Record<string, string> = {}
    if (config.token) headers['Authorization'] = `Bearer ${config.token}`
    const res = await fetch(config.server + '/api/upload', {
      method: 'POST', headers, body: fd,
    })
    if (!res.ok) throw new Error('Upload failed')
    return res.json()
  },
  resolveFileUrl(url: string): string {
    if (url.startsWith('http')) return url
    return config.server + url
  },
}
