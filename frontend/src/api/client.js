/** Axios HTTP 客户端：封装统一的请求实例和错误处理。 */
import axios from "axios";

const client = axios.create({
  baseURL: "/api/v1",   // 所有请求的基础路径
  timeout: 120000        // LLM 相关请求允许更长等待
});

/** 规范化错误载荷，统一提取 message 字段 */
function normalizeErrorPayload(payload, fallbackMessage) {
  if (!payload) {
    return { message: fallbackMessage };
  }

  if (typeof payload === "string") {
    return { message: payload };
  }

  // 处理 FastAPI 的 detail 嵌套结构
  if (payload.detail && typeof payload.detail === "object") {
    return normalizeErrorPayload(payload.detail, fallbackMessage);
  }

  return {
    ...payload,
    message: payload.message || fallbackMessage
  };
}

// 响应拦截器
client.interceptors.response.use(
  (response) => response.data,                                           // 成功：提取 data 字段
  (error) => {
    const payload = error.response?.data?.detail || error.response?.data; // 失败：提取错误详情
    return Promise.reject(normalizeErrorPayload(payload, error.message || "request failed"));
  }
);

export default client;
