import { BrowserRouter, Route, Routes } from "react-router-dom";
import Header from "./components/Header";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import Projects from "./pages/Projects";
import ProjectDetail from "./pages/ProjectDetail";
import Assets from "./pages/Assets";
import Scans from "./pages/Scans";

export default function App() {
  return (
    <BrowserRouter>
      <div className="h-screen flex flex-col">
        <Header />
        <div className="flex-1 flex overflow-hidden">
          <Sidebar />
          <main className="flex-1 overflow-y-auto p-6">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/projects" element={<Projects />} />
              <Route path="/projects/:name" element={<ProjectDetail />} />
              <Route path="/assets" element={<Assets />} />
              <Route path="/scans" element={<Scans />} />
            </Routes>
          </main>
        </div>
      </div>
    </BrowserRouter>
  );
}
