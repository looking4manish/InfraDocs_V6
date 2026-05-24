import axios from "axios";

// No hardcoded password fallback — the deployed JS bundle must not contain
// real credentials. If localStorage is empty (first visit, post-cache-clear,
// fresh browser), we send an empty password; the API returns 401 with a
// WWW-Authenticate: Basic header, and the browser shows its native auth
// prompt. setCreds() persists what the user types for subsequent loads.
const DEV_USER = "msinha";

export function getCreds() {
  return {
    username: localStorage.getItem("ifd_user") || DEV_USER,
    password: localStorage.getItem("ifd_pass") || "",
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

// On 401, persist the failed creds → "" so the next request from this page
// load also fails cleanly (instead of looping with stale auth). The browser
// catches the 401+WWW-Authenticate and shows its native prompt.
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      const { password } = getCreds();
      if (password) {
        // Persisted creds are wrong — clear them so the next request triggers
        // the browser auth dialog instead of silently reusing the bad pass.
        localStorage.removeItem("ifd_pass");
      }
    }
    return Promise.reject(err);
  }
);

export const endpoints = {
  health: () => api.get("/api/health"),

  // assets (Phase 3)
  listAssets: (params = {}) => api.get("/api/assets/", { params }),
  assetCategories: () => api.get("/api/assets/categories"),
  getAsset: (id) => api.get(`/api/assets/${encodeURIComponent(id)}`),

  // projects (Phase 3)
  listProjects: () => api.get("/api/projects/list"),
  getProject: (name) => api.get(`/api/projects/${encodeURIComponent(name)}`),

  // applications (Phase 5+ correlated docs)
  listApplications: (params = {}) =>
    api.get("/api/applications/list", { params }),
  getApplication: (name) =>
    api.get(`/api/applications/${encodeURIComponent(name)}`),

  // ports registry (Phase 7B)
  listPorts: (params = {}) => api.get("/api/ports/", { params }),
  portsSummary: () => api.get("/api/ports/summary"),
  probePorts: (range, proto = "tcp") =>
    api.get("/api/ports/probe", { params: { range, proto } }),

  // storage registry (Phase 7C)
  listStorage: (params = {}) => api.get("/api/storage/", { params }),
  storageSummary: () => api.get("/api/storage/summary"),

  // scans (Phase 3)
  listScans: (limit = 25) => api.get("/api/scans/", { params: { limit } }),
  getScan: (id) => api.get(`/api/scans/${id}`),
  triggerScan: () => api.post("/api/scans/trigger"),

  // actions (Phase 8)
  allowedActions: () => api.get("/api/actions/allowed"),
  listActions: (params = {}) => api.get("/api/actions/", { params }),
  fireAssetAction: (assetId, action, args = {}) =>
    api.post(`/api/assets/${encodeURIComponent(assetId)}/action`, {
      action,
      args,
    }),
  fireApplicationAction: (name, action, args = {}) =>
    api.post(`/api/applications/${encodeURIComponent(name)}/action`, {
      action,
      args,
    }),
};
