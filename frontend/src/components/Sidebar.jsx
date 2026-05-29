import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, Boxes, Folders, Plug, Database, Layers,
  ScanLine, History, Container, Package, Files, Cog, Clock, Globe, Network, HardDrive,
} from "lucide-react";
import { endpoints } from "../api/client";
import { cn } from "../lib/cn";

function NavItem({ to, icon: Icon, children, count, end = true }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-2.5 px-2.5 h-8 rounded-md text-[13px] transition",
          isActive
            ? "bg-accent/15 text-white"
            : "text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.04]"
        )
      }
    >
      {Icon && <Icon size={15} className="shrink-0 opacity-90" />}
      <span className="truncate">{children}</span>
      {typeof count === "number" && (
        <span className="ml-auto text-[11px] text-zinc-600 tabular-nums">{count}</span>
      )}
    </NavLink>
  );
}

function SectionLabel({ children }) {
  return (
    <div className="px-2.5 mt-5 mb-1.5 text-[10px] font-medium uppercase tracking-[0.08em] text-zinc-600">
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
    <aside className="w-60 shrink-0 border-r border-bg-hover bg-bg-panel py-3 px-2 overflow-y-auto">
      <SectionLabel>Overview</SectionLabel>
      <div className="space-y-0.5">
        <NavItem to="/" icon={LayoutDashboard}>Dashboard</NavItem>
      </div>

      <SectionLabel>Inventory</SectionLabel>
      <div className="space-y-0.5">
        <NavItem to="/applications" icon={Boxes} count={apps.data} end={false}>
          Applications
        </NavItem>
        <NavItem to="/projects" icon={Folders} end={false}>Projects</NavItem>
        <NavItem to="/ports" icon={Plug} count={ports.data}>Ports</NavItem>
        <NavItem to="/storage" icon={Database} count={storage.data}>Storage</NavItem>
        <NavItem to="/assets" icon={Layers}>All Assets</NavItem>
      </div>

      <SectionLabel>Activity</SectionLabel>
      <div className="space-y-0.5">
        <NavItem to="/scans" icon={ScanLine}>Scans</NavItem>
        <NavItem to="/actions" icon={History}>Actions Log</NavItem>
      </div>

      <SectionLabel>By Category</SectionLabel>
      <div className="space-y-0.5">
        <NavItem to="/assets?category=docker_container" icon={Container} count={counts["docker_container"]}>
          Docker Containers
        </NavItem>
        <NavItem to="/assets?category=docker_image" icon={Package} count={counts["docker_image"]}>
          Docker Images
        </NavItem>
        <NavItem to="/assets?category=docker_compose" icon={Files} count={counts["docker_compose"]}>
          Compose Files
        </NavItem>
        <NavItem to="/assets?category=systemd_service" icon={Cog} count={counts["systemd_service"]}>
          Systemd Services
        </NavItem>
        <NavItem to="/assets?category=systemd_timer" icon={Clock} count={counts["systemd_timer"]}>
          Systemd Timers
        </NavItem>
        <NavItem to="/assets?category=nginx_server_block" icon={Globe} count={counts["nginx_server_block"]}>
          Nginx Sites
        </NavItem>
        <NavItem to="/assets?category=network_port" icon={Network} count={counts["network_port"]}>
          Network Ports
        </NavItem>
        <NavItem to="/assets?category=storage_mount" icon={HardDrive} count={counts["storage_mount"]}>
          Storage Mounts
        </NavItem>
      </div>
    </aside>
  );
}
