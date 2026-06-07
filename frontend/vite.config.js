/** Vite 构建配置：配置 Vue 插件、开发服务器端口和 API 代理。 */
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

const apiTarget = process.env.VITE_API_TARGET || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [vue()],       // 启用 Vue 3 SFC 编译
  server: {
    port: 5173,             // 开发服务器端口
    proxy: {
      "/api": {             // 将 /api 请求代理到后端 FastAPI 服务
        target: apiTarget,
        changeOrigin: true
      }
    }
  }
});
