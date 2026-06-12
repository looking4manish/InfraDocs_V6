import { useQuery } from "@tanstack/react-query";
import { endpoints } from "../api/client";

// Caches /api/actions/allowed (allowed + destructive maps) for the whole app.
// Backend is authoritative; the UI reads this to decide which buttons exist
// and which need a confirm gate.
export function useAllowedActions() {
  const q = useQuery({
    queryKey: ["actions-allowed"],
    queryFn: () => endpoints.allowedActions().then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });
  return {
    allowed: q.data?.allowed || {},
    destructive: q.data?.destructive || {},
    isLoading: q.isLoading,
  };
}
