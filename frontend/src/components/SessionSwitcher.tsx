import { useEffect, useRef, useState } from 'react'
import { createSession, listSessions, type SessionMeta } from '../lib/api'
import { useCurrentSessionId } from '../lib/useSession'

interface Props {
  disabled?: boolean
  onSessionChange?: () => void
}

export default function SessionSwitcher({ disabled, onSessionChange }: Props) {
  const [currentId, setCurrentId] = useCurrentSessionId()
  const [sessions, setSessions] = useState<SessionMeta[]>([])
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    listSessions()
      .then(setSessions)
      .catch(() => {
        /* silent — switcher just shows the persisted id as fallback */
      })
  }, [])

  useEffect(() => {
    if (!open) return
    const handler = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const currentMeta = sessions.find((s) => s.id === currentId)
  const label = currentMeta?.name ?? currentId

  const handlePick = (id: string) => {
    if (id !== currentId) {
      setCurrentId(id)
      onSessionChange?.()
    }
    setOpen(false)
  }

  const handleNew = async () => {
    setBusy(true)
    try {
      const created = await createSession()
      setSessions((curr) => [...curr, created])
      setCurrentId(created.id)
      onSessionChange?.()
      setOpen(false)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="text-xs text-amber-crt/60 uppercase tracking-widest border border-amber-crt/30 px-3 py-1.5 hover:bg-amber-crt/10 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
      >
        <span>session:</span>
        <span className="text-signal normal-case tracking-normal">{label}</span>
        <span aria-hidden className="text-amber-crt/60">
          {open ? '▴' : '▾'}
        </span>
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 mt-2 border border-amber-crt/30 bg-black z-20 min-w-56 max-h-72 overflow-y-auto"
        >
          {sessions.length === 0 && (
            <div className="px-3 py-2 text-xs text-amber-crt/50">loading…</div>
          )}
          {sessions.map((s) => (
            <button
              key={s.id}
              type="button"
              role="menuitem"
              onClick={() => handlePick(s.id)}
              className="flex items-center justify-between w-full text-left px-3 py-2 text-xs hover:bg-amber-crt/10"
            >
              <span className={s.id === currentId ? 'text-amber-crt' : 'text-amber-crt/70'}>
                {s.name}
              </span>
              {s.id === currentId && <span className="text-signal text-base">●</span>}
            </button>
          ))}
          <button
            type="button"
            role="menuitem"
            disabled={busy}
            onClick={handleNew}
            className="block w-full text-left px-3 py-2 text-xs text-signal border-t border-amber-crt/20 hover:bg-amber-crt/10 disabled:opacity-50"
          >
            {busy ? '…' : '+ new session'}
          </button>
        </div>
      )}
    </div>
  )
}
