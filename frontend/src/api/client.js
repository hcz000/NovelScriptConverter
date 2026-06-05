import axios from "axios";

const client = axios.create({
  baseURL: "/api/v1",
  timeout: 30000
});

client.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const payload = error.response?.data?.detail || error.response?.data;
    return Promise.reject(payload || { message: error.message || "request failed" });
  }
);

export default client;
