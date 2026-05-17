/**
 * Tiny path router built on the browser history API. ~30 lines, no deps.
 *
 * Why not react-router: we have exactly two routes (`/` and `/works`) and
 * the nginx site already falls back any unknown path to index.html, so
 * direct URL access + refresh just works. Pulling in react-router for two
 * routes would be 30 KB gzipped vs the 200 bytes here.
 */

import { useEffect, useState } from 'react'

/** Subscribe to the current URL path. Re-renders on pushState + popstate. */
export function usePath(): string {
  const [path, setPath] = useState(window.location.pathname)
  useEffect(() => {
    function update() {
      setPath(window.location.pathname)
    }
    window.addEventListener('popstate', update)
    // Custom event we dispatch from `navigate()` so pushState callers refresh.
    window.addEventListener('routechange', update)
    return () => {
      window.removeEventListener('popstate', update)
      window.removeEventListener('routechange', update)
    }
  }, [])
  return path
}

/** Programmatic navigation. Use this instead of <a href> for in-app links. */
export function navigate(to: string): void {
  if (to === window.location.pathname) return
  window.history.pushState({}, '', to)
  window.dispatchEvent(new Event('routechange'))
  // Scroll to top so /works doesn't load mid-scroll from where the user was.
  window.scrollTo(0, 0)
}

/**
 * A `<Link>` substitute. Plain `<a>` would cause a full page navigation,
 * losing React state and the SPA feel. This handles click + meta/ctrl-click
 * (open in new tab) sensibly without depending on react-router.
 */
export function linkProps(to: string): {
  href: string
  onClick: (e: React.MouseEvent<HTMLAnchorElement>) => void
} {
  return {
    href: to,
    onClick(e) {
      // Let the browser handle modified clicks normally (new tab etc).
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
      e.preventDefault()
      navigate(to)
    },
  }
}
