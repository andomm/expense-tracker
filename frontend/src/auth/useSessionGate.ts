import { useCallback, useLayoutEffect, useRef, useState } from "react"
import { flushSync } from "react-dom"

import type { AppConfig } from "@/Shell"
import { PROTECTED_SESSION_REJECTED, readJson, submitAuth, type Session } from "@/lib/api"

import { sessionChannelName, type SessionEvent } from "./session-events"

type Gate = { kind: "checking" | "unavailable" | "signing-out" | "leaving" }
  | { kind: "active" | "expired"; session: Session }

export function useSessionGate({ urls, userId }: AppConfig, keepDraft: boolean) {
  const [gate, setGate] = useState<Gate>({ kind: "checking" })
  const [ownerSession, setOwnerSession] = useState<Session | null>(null)
  const [readVersion, setReadVersion] = useState(0)
  const [logoutError, setLogoutError] = useState(false)
  const [resumed, setResumed] = useState(false)
  const marker = useRef<string | null | undefined>(undefined)
  const expired = useRef(false)
  const check = useRef<AbortController | null>(null)
  const logout = useRef<AbortController | null>(null)
  const channel = useRef<BroadcastChannel | null>(null)

  const accept = useCallback((session: Session) => {
    check.current?.abort()
    check.current = null
    const explicitlyLoggedOut = marker.current !== undefined && marker.current !== session.logout_marker
    marker.current = session.logout_marker

    if (session.user && session.user.id !== userId) {
      // Never reuse the previous account's page config or object URLs.
      flushSync(() => {
        setOwnerSession(null)
        setGate({ kind: "leaving" })
      })
      window.location.replace(urls.expenses)
    } else if (session.user) {
      if (explicitlyLoggedOut) {
        flushSync(() => setOwnerSession(null))
      }
      if (expired.current || explicitlyLoggedOut) {
        setReadVersion((version) => version + 1)
        setResumed(!explicitlyLoggedOut && expired.current && keepDraft)
      }
      expired.current = false
      setOwnerSession(session)
      setGate({ kind: "active", session })
    } else {
      expired.current = true
      setResumed(false)
      if (!keepDraft || explicitlyLoggedOut) setOwnerSession(null)
      setGate({ kind: "expired", session })
    }
  }, [keepDraft, urls.expenses, userId])

  const revalidate = useCallback(() => {
    if (check.current || logout.current || document.visibilityState !== "visible") return
    const controller = new AbortController()
    check.current = controller
    setGate({ kind: "checking" })
    void readJson<Session>(urls.sessionApi, controller.signal).then((current) => {
      if (!controller.signal.aborted) accept(current)
    }).catch(() => {
      if (!controller.signal.aborted) {
        check.current = null
        setGate({ kind: "unavailable" })
      }
    })
  }, [accept, urls.sessionApi])

  useLayoutEffect(() => {
    function freeze() {
      check.current?.abort()
      check.current = null
      // A restored document must be hidden before the browser paints it.
      if (!logout.current) flushSync(() => setGate({ kind: "checking" }))
    }
    function visibility() {
      if (document.visibilityState === "visible") revalidate()
      else freeze()
    }
    function sessionRejected() {
      // A check that began before this rejection may have read the old cookies.
      freeze()
      revalidate()
    }
    function restore(event: PageTransitionEvent) {
      if (!event.persisted) return
      // Re-read cached lists, charts, and confirmations after leaving the page.
      // Editors stay mounted so a verified owner can resume an unsaved draft.
      if (!keepDraft) setOwnerSession(null)
      sessionRejected()
    }
    if (typeof BroadcastChannel !== "undefined") {
      channel.current = new BroadcastChannel(sessionChannelName)
      channel.current.onmessage = (event: MessageEvent<SessionEvent>) => {
        if (event.data?.kind === "signed-out" && event.data.marker !== marker.current) {
          setOwnerSession(null)
          setResumed(false)
        }
        sessionRejected()
      }
    }
    document.addEventListener("visibilitychange", visibility)
    window.addEventListener("focus", revalidate)
    window.addEventListener("pagehide", freeze)
    window.addEventListener("pageshow", restore)
    window.addEventListener(PROTECTED_SESSION_REJECTED, sessionRejected)
    revalidate()
    return () => {
      check.current?.abort()
      logout.current?.abort()
      check.current = null
      logout.current = null
      channel.current?.close()
      document.removeEventListener("visibilitychange", visibility)
      window.removeEventListener("focus", revalidate)
      window.removeEventListener("pagehide", freeze)
      window.removeEventListener("pageshow", restore)
      window.removeEventListener(PROTECTED_SESSION_REJECTED, sessionRejected)
    }
  }, [keepDraft, revalidate])

  async function signOut() {
    if (gate.kind !== "active" || logout.current) return
    const controller = new AbortController()
    logout.current = controller
    flushSync(() => {
      setOwnerSession(null)
      setGate({ kind: "signing-out" })
      setLogoutError(false)
      setResumed(false)
    })
    try {
      const result = await submitAuth(urls.logoutApi, gate.session, {}, controller.signal)
      if (controller.signal.aborted) return
      channel.current?.postMessage({ kind: "signed-out", marker: result.logout_marker } satisfies SessionEvent)
      window.location.replace(result.next)
    } catch {
      if (controller.signal.aborted) return
      setLogoutError(true)
      logout.current = null
      revalidate()
    }
  }

  return { gate, ownerSession, readVersion, resumed, logoutError, revalidate, accept, signOut }
}
