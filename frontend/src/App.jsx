import { useEffect, useState, useCallback } from "react";
import { BrowserRouter, Route, Routes, Outlet, Navigate, useParams, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import { endpoints, isAuthed, clearToken } from "./api/client";
import { Login, ChangePassword } from "./pages/Login";
import Header from "./components/Header";
import DrawerProvider from "./components/DrawerProvider";
import CommandPalette from "./components/CommandPalette";
import LensHome from "./pages/LensHome";
import Projects from "./pages/Projects";
import ProjectDetail from "./pages/ProjectDetail";
import Applications from "./pages/Applications";
import Assets from "./pages/Assets";
import Ports from "./pages/Ports";
import Storage from "./pages/Storage";
import Actions from "./pages/Actions";
import Scans from "./pages/Scans";

// Old detail links (/applications/<name>) fold into the master-detail split view,
// which carries the selection in ?sel= so the list stays mounted.
function AppDetailRedirect() {
  const { name } = useParams();
  return <Navigate to={`/applications?sel=${encodeURIComponent(name)}`} replace />;
}

function AppShell() {
  const location = useLocation();
  return (
    <div className="h-screen flex flex-col">
      <Header />
      <div className="flex-1 flex overflow-hidden">
        <main className="flex-1 overflow-y-auto">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.18, ease: "easeOut" }}
              className="p-6"
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}

// Gates the whole app behind login. Verifies the stored token via /me, forces
// a password change when flagged, and falls back to the login screen on 401.
function AuthGate({ children }) {
  const [status, setStatus] = useState("loading"); // loading | login | change | ready

  const refresh = useCallback(async () => {
    if (!isAuthed()) return setStatus("login");
    try {
      const { data } = await endpoints.me();
      setStatus(data.must_change_password ? "change" : "ready");
    } catch {
      clearToken();
      setStatus("login");
    }
  }, []);

  useEffect(() => {
    refresh();
    const onUnauth = () => setStatus("login");
    window.addEventListener("ifd-unauthorized", onUnauth);
    return () => window.removeEventListener("ifd-unauthorized", onUnauth);
  }, [refresh]);

  if (status === "loading") return <div className="min-h-screen bg-[#0a0e14]" />;
  if (status === "login")
    return (
      <Login
        onLoggedIn={(d) => setStatus(d.must_change_password ? "change" : "ready")}
      />
    );
  if (status === "change")
    return <ChangePassword onDone={() => setStatus("ready")} />;
  return children;
}

export default function App() {
  return (
    <AuthGate>
    <BrowserRouter>
      <DrawerProvider>
        <CommandPalette />
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<LensHome />} />
            {/* Dashboard now lives as a lens on "/"; keep the old path deep-linkable. */}
            <Route path="/dashboard" element={<Navigate to="/" replace />} />
            <Route path="/applications" element={<Applications />} />
            <Route path="/applications/:name" element={<AppDetailRedirect />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/projects/:name" element={<ProjectDetail />} />
            <Route path="/assets" element={<Assets />} />
            <Route path="/ports" element={<Ports />} />
            <Route path="/storage" element={<Storage />} />
            <Route path="/actions" element={<Actions />} />
            <Route path="/scans" element={<Scans />} />
          </Route>
        </Routes>
      </DrawerProvider>
    </BrowserRouter>
    </AuthGate>
  );
}
