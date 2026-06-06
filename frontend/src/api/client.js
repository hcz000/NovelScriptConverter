import axios from "axios";

const client = axios.create({
  baseURL: "/api/v1",
  timeout: 30000
});

function normalizeErrorPayload(payload, fallbackMessage) {
  if (!payload) {
    return { message: fallbackMessage };
  }

  if (typeof payload === "string") {
    return { message: payload };
  }

  if (payload.detail && typeof payload.detail === "object") {
    return normalizeErrorPayload(payload.detail, fallbackMessage);
  }

  return {
    ...payload,
    message: payload.message || fallbackMessage
  };
}

client.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const payload = error.response?.data?.detail || error.response?.data;
    return Promise.reject(normalizeErrorPayload(payload, error.message || "request failed"));
  }
);

export default client;
