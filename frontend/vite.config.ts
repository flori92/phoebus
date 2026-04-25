import { defineConfig } from "vite";

export default defineConfig({
  server: {
    host: "0.0.0.0",
    port: 5173, // Ce port sera surchargé par la ligne de commande dans main2.py
    allowedHosts: ["phoebus.local", "localhost", "127.0.0.1"],
  },
  build: {
    outDir: "dist",
  },
});
