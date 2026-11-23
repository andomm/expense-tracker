import { createContext, useContext } from "react"

export const ProtectedAccess = createContext({ active: true, readVersion: 0 })

export function useProtectedActive() {
  return useContext(ProtectedAccess).active
}
