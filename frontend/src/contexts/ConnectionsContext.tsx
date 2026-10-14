"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "@/services/api";
import { useAuth } from "@/contexts/AuthContext";
import type { Integration } from "@/types";

interface ConnectionsContextType {
  integrations: Integration[];
  isConfigured: boolean;
  loading: boolean;
  refreshConnections: () => Promise<void>;
}

const REQUIRED_TYPES = ["jira", "confluence", "github"] as const;

const ConnectionsContext = createContext<ConnectionsContextType | undefined>(undefined);

export function ConnectionsProvider({ children }: { children: React.ReactNode }) {
  const { token, isLoading: authLoading } = useAuth();
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);

  const refreshConnections = useCallback(async () => {
    // Without an auth token the /integrations request would come back 401 and
    // get silently collapsed to an empty list. Skip until we're authenticated.
    if (!token) {
      setIntegrations([]);
      return;
    }

    const result = await api.get<Integration[]>("/integrations");
    if (result.data) {
      setIntegrations(result.data);
    } else {
      setIntegrations([]);
    }
  }, [token]);

  useEffect(() => {
    // Wait for auth to finish restoring/validating the session, then fetch.
    // Re-runs whenever the token changes (login/logout) so all consumers stay
    // in sync instead of being stuck with a stale unauthenticated result.
    if (authLoading) {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      void refreshConnections().finally(() => setLoading(false));
    }, 0);

    return () => window.clearTimeout(timeoutId);
  }, [authLoading, refreshConnections]);

  const isConfigured = REQUIRED_TYPES.every((type) =>
    integrations.some((i) => i.type === type),
  );

  const value = useMemo<ConnectionsContextType>(
    () => ({ integrations, isConfigured, loading, refreshConnections }),
    [integrations, isConfigured, loading, refreshConnections],
  );

  return (
    <ConnectionsContext.Provider value={value}>
      {children}
    </ConnectionsContext.Provider>
  );
}

export function useConnections() {
  const context = useContext(ConnectionsContext);
  if (!context) {
    throw new Error("useConnections must be used within a ConnectionsProvider");
  }
  return context;
}