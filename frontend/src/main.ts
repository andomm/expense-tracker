import "vite/modulepreload-polyfill"
import "@fontsource-variable/manrope"
import "./app.css"

import { createElement } from "react"
import { createRoot } from "react-dom/client"

import { App } from "./App"
import { AuthPage, type AuthConfig } from "./auth/AuthPage"
import type { AppConfig } from "./Shell"

const config = JSON.parse(document.getElementById("app-config")!.textContent!) as AppConfig | AuthConfig
const root = createRoot(document.getElementById("app")!)
if ("next" in config) {
  // Auth documents should re-open with a fresh token, not old credentials.
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) window.location.reload()
  })
  root.render(createElement(AuthPage, { config }))
} else {
  root.render(createElement(App, { config }))
}
