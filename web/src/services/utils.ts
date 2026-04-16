// Generate a stable color from a username. Used for usernames in group chats.
const PALETTE = [
  '#50c878', // green phosphor
  '#ff9933', // orange
  '#ffd166', // amber
  '#4dabff', // blue
  '#e879f9', // pink
  '#22d3ee', // cyan
  '#a78bfa', // violet
  '#fb7185', // rose
  '#facc15', // yellow
]

export function userColor(username: string): string {
  let h = 0
  for (let i = 0; i < username.length; i++) {
    h = (h * 31 + username.charCodeAt(i)) >>> 0
  }
  return PALETTE[h % PALETTE.length]
}

export function fmtTime(iso: string): string {
  try {
    const d = new Date(iso)
    const hh = d.getHours().toString().padStart(2, '0')
    const mm = d.getMinutes().toString().padStart(2, '0')
    const ss = d.getSeconds().toString().padStart(2, '0')
    return `${hh}:${mm}:${ss}`
  } catch {
    return '--:--:--'
  }
}

export function fmtTimeShort(iso: string): string {
  try {
    const d = new Date(iso)
    const now = new Date()
    if (d.toDateString() === now.toDateString()) {
      return d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0')
    }
    const diff = (now.getTime() - d.getTime()) / 86400000
    if (diff < 7) {
      return ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'][d.getDay()]
    }
    return d.getDate().toString().padStart(2, '0') + '/' + (d.getMonth() + 1).toString().padStart(2, '0')
  } catch {
    return ''
  }
}

export function linkify(text: string): (string | { url: string })[] {
  const re = /(https?:\/\/[^\s)]+)/g
  const out: (string | { url: string })[] = []
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index))
    out.push({ url: m[1] })
    last = m.index + m[1].length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}
