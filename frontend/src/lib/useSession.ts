import { useSyncExternalStore } from 'react'

const STORAGE_KEY = 'bark-to-game/session-id'
const DEFAULT_ID = 'default'

const listeners = new Set<() => void>()

function subscribe(fn: () => void): () => void {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}

function readSnapshot(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? DEFAULT_ID
  } catch {
    // jsdom or SSR-like environments may not expose localStorage.
    return DEFAULT_ID
  }
}

function writeId(id: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, id)
  } catch {
    // Same fallback — still notify in-memory subscribers below.
  }
  listeners.forEach((fn) => fn())
}

export function useCurrentSessionId(): [string, (id: string) => void] {
  const id = useSyncExternalStore(subscribe, readSnapshot, () => DEFAULT_ID)
  return [id, writeId]
}
