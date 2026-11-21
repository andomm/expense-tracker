import "vite/modulepreload-polyfill"
import "@fontsource-variable/manrope"
import "./app.css"

import { createElement } from "react"
import { createRoot } from "react-dom/client"

import { App } from "./App"
import type { AppConfig } from "./Shell"

// Revalidate private data if history navigation restores a frozen document.
window.addEventListener("pageshow", (event) => {
  if (event.persisted) {
    window.location.reload()
  }
})

const config = JSON.parse(document.getElementById("app-config")!.textContent!) as AppConfig
const root = createRoot(document.getElementById("app")!)
root.render(createElement(App, { config }))
