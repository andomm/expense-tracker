// No user IDs, credentials, or drafts travel between tabs.
export const sessionChannelName = "expense:session"
export type SessionEvent = { kind: "signed-in" } | { kind: "signed-out"; marker: string | null }

export function notifySignIn() {
  if (typeof BroadcastChannel === "undefined") return
  const channel = new BroadcastChannel(sessionChannelName)
  channel.postMessage({ kind: "signed-in" } satisfies SessionEvent)
  channel.close()
}
