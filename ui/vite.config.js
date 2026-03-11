import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // UI calls /v1/* and Vite proxies to API container
      "/v1": "http://api:8000",
    },
  },
});