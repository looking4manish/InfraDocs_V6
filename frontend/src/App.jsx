import { BrowserRouter, Route, Routes, Outlet, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import Header from "./components/Header";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import Projects from "./pages/Projects";
import ProjectDetail from "./pages/ProjectDetail";
import Applications from "./pages/Applications";
import ApplicationDetail from "./pages/ApplicationDetail";
import Assets from "./pages/Assets";
import Ports from "./pages/Ports";
import Storage from "./pages/Storage";
import Actions from "./pages/Actions";
import Scans from "./pages/Scans";

function AppShell() {
  const location = useLocation();
  return (
    <div className="h-screen flex flex-col">
      <Header />
      <div className="flex-1 flex overflow-hidden">
        <Sidebar />
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

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/applications" element={<Applications />} />
          <Route path="/applications/:name" element={<ApplicationDetail />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/projects/:name" element={<ProjectDetail />} />
          <Route path="/assets" element={<Assets />} />
          <Route path="/ports" element={<Ports />} />
          <Route path="/storage" element={<Storage />} />
          <Route path="/actions" element={<Actions />} />
          <Route path="/scans" element={<Scans />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
