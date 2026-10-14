"use client";

import { useConnections } from "@/contexts/ConnectionsContext";

/**
 * Hook that checks whether the current user has configured integrations
 * for all three required services: Jira, Confluence, and GitHub.
 *
 * Returns `isConfigured: true` only when at least one integration record
 * exists for each of these three service types.
 *
 * Data is sourced from the shared ConnectionsContext, so all consumers
 * stay in sync automatically.
 */
export function useRequiredConnections() {
  const { isConfigured, loading, refreshConnections, integrations } = useConnections();
  return { isConfigured, loading, refresh: refreshConnections, integrations };
}