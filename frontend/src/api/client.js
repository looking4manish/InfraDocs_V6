import axios from "axios";

const DEV_USER = "msinha";
const DEV_PASS = "msinha123";

export function getCreds() {
  return {
    username: localStorage.getItem("ifd_user") || DEV_USER,
    password: localStorage.getItem("ifd_pass") || DEV_PASS,
  };
}

export function setCreds(username, password) {
  localStorage.setItem("ifd_user", username);
  localStorage.setItem("ifd_pass", password);
}

export const api = axios.create({
  baseURL: "",
  timeout: 30000,
});

api.interceptors.request.use((config) => {
  const { username, password } = getCreds();
  const token = btoa(`${username}:${password}`);
  config.headers.Authorization = `Basic ${token}`;
  return config;
});

export const endpoints = {
  health: () => api.get("/api/health"),

  listAssets: (params = {}) => api.get("/api/assets/", { params }),
  assetCategories: () => api.get("/api/assets/categories"),
  getAsset: (id) => api.get(`/api/assets/${encodeURIComponent(id)}`),

  listProjects: () => api.get("/api/projects/list"),
  getProject: (name) => api.get(`/api/projects/${encodeURIComponent(name)}`),

  listScans: (limit = 25) => api.get("/api/scans/", { params: { limit } }),
  getScan: (id) => api.get(`/api/scans/${id}`),
  triggerScan: () => api.post("/api/scans/trigger"),
};
