import axios from "axios";

// Session-token auth: login → opaque token → sent as `Authorization: Bearer`.
// No credentials ever live in the JS bundle or persist beyond the token.
const TOKEN_KEY = "ifd_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}
export function setToken(t) {
  localStorage.setItem(TOKEN_KEY, t);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}
export function isAuthed() {
  return !!getToken();
}

export const api = axios.create({
  baseURL: "",
  timeout: 30000,
});

api.interceptors.request.use((config) => {
  const t = getToken();
  if (t) config.headers.Authorization = `Bearer ${t}`;
  return config;
});

// On 401, drop the (now invalid/expired) token and let the app fall back to
// the login screen instead of looping with a dead session.
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401 && getToken()) {
      clearToken();
      window.dispatchEvent(new Event("ifd-unauthorized"));
    }
    return Promise.reject(err);
  }
);

export const endpoints = {
  health: () => api.get("/api/health"),

  // auth
  login: (username, password) =>
    api.post("/api/auth/login", { username, password }),
  me: () => api.get("/api/auth/me"),
  changePassword: (new_password) =>
    api.post("/api/auth/change-password", { new_password }),
  logout: () => api.post("/api/auth/logout"),

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
  blastRadius: (name) =>
    api.get(`/api/applications/${encodeURIComponent(name)}/blast-radius`),
  teardown: (name, body) =>
    api.post(`/api/applications/${encodeURIComponent(name)}/teardown`, body),

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
