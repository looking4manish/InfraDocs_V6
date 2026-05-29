import { useNavigate } from "react-router-dom";
import { X } from "lucide-react";
import ApplicationDetail from "./ApplicationDetail";

export default function ApplicationPanel() {
  const navigate = useNavigate();
  return (
    <div className="flex flex-col h-full">
      <div className="shrink-0 flex items-center justify-end px-3 py-2 border-b border-bg-hover bg-bg-panel">
        <button
          onClick={() => navigate("/applications")}
          aria-label="Close panel"
          className="p-1.5 rounded hover:bg-bg-hover text-slate-400 hover:text-slate-100 transition"
        >
          <X size={18} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-5 py-4">
        <ApplicationDetail />
      </div>
    </div>
  );
}
