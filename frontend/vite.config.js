import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  envDir: process.env.ENV_DIR ?? false,
  plugins: [vue()],
});
