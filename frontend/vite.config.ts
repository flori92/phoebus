import { defineConfig } from "vite";
import basicSsl from "@vitejs/plugin-basic-ssl";

export default defineConfig({
  plugins: [basicSsl()],
  server: {
    https: true,
    host: "0.0.0.0",
    port: 5173, // Ce port sera surchargé par la ligne de commande dans main2.py
    allowedHosts: ["phoebus.local", "localhost", "127.0.0.1"],
  },
  build: {
    outDir: "dist",
  },
});
