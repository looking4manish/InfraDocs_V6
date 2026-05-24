import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";
import { endpoints } from "../api/client";

function NavItem({ to, children, count, end = true }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `flex items-center justify-between px-3 py-1.5 rounded text-sm ${
          isActive
            ? "bg-accent/20 text-accent"
            : "text-slate-300 hover:bg-bg-hover"
        }`
      }
    >
      <span>{children}</span>
      {typeof count === "number" && (
        <span className="text-xs text-slate-500">{count}</span>
      )}
    </NavLink>
  );
}

function SectionLabel({ children }) {
  return (
    <div className="px-3 mt-4 mb-1 text-xs uppercase tracking-wide text-slate-500">
      {children}
    </div>
  );
}

export default function Sidebar() {
  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: () => endpoints.assetCategories().then((r) => r.data.categories),
  });
  const apps = useQuery({
    queryKey: ["applications-count"],
    queryFn: () => endpoints.listApplications().then((r) => r.data.count),
  });
  const ports = useQuery({
    queryKey: ["ports-count"],
    queryFn: () => endpoints.portsSummary().then((r) => r.data.total),
  });
  const storage = useQuery({
    queryKey: ["storage-count"],
    queryFn: () => endpoints.storageSummary().then((r) => r.data.total),
  });

  const counts = Object.fromEntries(
    (categories.data || []).map((c) => [c.category, c.count])
  );

  return (
    <aside className="w-60 border-r border-bg-card bg-bg-panel py-3 overflow-y-auto">
      <SectionLabel>Overview</SectionLabel>
      <div className="px-2 space-y-1">
        <NavItem to="/">Dashboard</NavItem>
      </div>

      <SectionLabel>Inventory</SectionLabel>
      <div className="px-2 space-y-1">
        <NavItem to="/applications" count={apps.data} end={false}>
          Applications
        </NavItem>
        <NavItem to="/projects" end={false}>Projects</NavItem>
        <NavItem to="/ports" count={ports.data}>Ports</NavItem>
        <NavItem to="/storage" count={storage.data}>Storage</NavItem>
        <NavItem to="/assets">All Assets</NavItem>
      </div>

      <SectionLabel>Activity</SectionLabel>
      <div className="px-2 space-y-1">
        <NavItem to="/scans">Scans</NavItem>
        <NavItem to="/actions">Actions Log</NavItem>
      </div>

      <SectionLabel>By Category</SectionLabel>
      <div className="px-2 space-y-1">
        <NavItem
          to="/assets?category=docker_container"
          count={counts["docker_container"]}
        >
          Docker Containers
        </NavItem>
        <NavItem to="/assets?category=docker_image" count={counts["docker_image"]}>
          Docker Images
        </NavItem>
        <NavItem
          to="/assets?category=docker_compose"
          count={counts["docker_compose"]}
        >
          Compose Files
        </NavItem>
        <NavItem
          to="/assets?category=systemd_service"
          count={counts["systemd_service"]}
        >
          Systemd Services
        </NavItem>
        <NavItem
          to="/assets?category=systemd_timer"
          count={counts["systemd_timer"]}
        >
          Systemd Timers
        </NavItem>
        <NavItem
          to="/assets?category=nginx_server_block"
          count={counts["nginx_server_block"]}
        >
          Nginx Sites
        </NavItem>
        <NavItem to="/assets?category=network_port" count={counts["network_port"]}>
          Network Ports
        </NavItem>
        <NavItem to="/assets?category=storage_mount" count={counts["storage_mount"]}>
          Storage Mounts
        </NavItem>
      </div>
    </aside>
  );
}
