import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { fileURLToPath } from "node:url"
import { defineConfig } from "vite"

const vitePort = Number(process.env.VITE_PORT ?? 5173)

export default defineConfig({
  appType: "custom",
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    host: "localhost",
    port: vitePort,
    origin: `http://localhost:${vitePort}`,
    strictPort: true,
    cors: { origin: [`http://127.0.0.1:${process.env.DJANGO_PORT ?? 8000}`] },
  },
  build: {
    rolldownOptions: { input: fileURLToPath(new URL("./src/main.ts", import.meta.url)) },
  },
})
