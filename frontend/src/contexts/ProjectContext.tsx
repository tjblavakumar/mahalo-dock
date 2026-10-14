"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/services/api";
import { useAuth } from "@/contexts/AuthContext";
import { useConnections } from "@/contexts/ConnectionsContext";
import type { Project } from "@/types";

interface ProjectContextType {
  projects: Project[];
  activeProject: Project | null;
  selectedProjects: Project[];
  loading: boolean;
  syncing: boolean;
  refreshProjects: () => Promise<void>;
  syncProjects: () => Promise<void>;
  setActiveProject: (projectId: number) => Promise<boolean>;
  toggleProjectSelection: (projectId: number) => Promise<boolean>;
}

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const { token, isLoading: authLoading } = useAuth();
  const { integrations, loading: connectionsLoading } = useConnections();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  // Ensures the one-time auto-sync from connections runs at most once per token.
  const autoSyncedRef = useRef<string | null>(null);

  const refreshProjects = useCallback(async () => {
    // Without an auth token the /projects request would 401 and collapse to an
    // empty list, leaving the sidebar stuck on "No projects yet". Skip until
    // we're authenticated (mirrors ConnectionsContext).
    if (!token) {
      setProjects([]);
      return;
    }

    const result = await api.get<Project[]>("/projects");
    if (result.data) {
      setProjects(result.data);
      return;
    }
    setProjects([]);
  }, [token]);

  // Import projects that exist in the connected Jira into the local list. The
  // backend upserts anything not already linked and returns the full list.
  const syncProjects = useCallback(async () => {
    if (!token) return;
    setSyncing(true);
    try {
      const result = await api.post<Project[]>("/projects/sync", {});
      if (result.data) {
        setProjects(result.data);
      }
    } finally {
      setSyncing(false);
    }
  }, [token]);

  useEffect(() => {
    // Wait for auth to finish restoring/validating the session, then fetch.
    // Re-runs whenever the token changes (login/logout) so the projects list
    // stays in sync instead of being stuck with a stale unauthenticated result.
    if (authLoading) {
      return;
    }
    let cancelled = false;
    async function init() {
      await refreshProjects();
      if (!cancelled) setLoading(false);
    }
    void init();
    return () => {
      cancelled = true;
    };
  }, [authLoading, refreshProjects]);

  // Once, after both projects and connections have loaded, pull any projects
  // that exist in the connected Jira into the local list. Guarded per-token so
  // it runs only once per session and doesn't fight manual syncs/refreshes.
  const hasJira = useMemo(
    () => integrations.some((i) => i.type === "jira"),
    [integrations]
  );
  useEffect(() => {
    if (authLoading || connectionsLoading || loading) return;
    if (!token || !hasJira) return;
    if (autoSyncedRef.current === token) return;

    autoSyncedRef.current = token;
    // Defer so the synchronous setState in syncProjects doesn't run in the
    // effect body (react-hooks/set-state-in-effect).
    queueMicrotask(() => {
      void syncProjects();
    });
  }, [authLoading, connectionsLoading, loading, token, hasJira, syncProjects]);

  const selectedProjects = useMemo(() => {
    return projects.filter((project) => project.is_selected);
  }, [projects]);

  const activeProject = useMemo(() => {
    return projects.find((project) => project.is_active) ?? selectedProjects[0] ?? projects[0] ?? null;
  }, [projects, selectedProjects]);

  const setActiveProject = useCallback(async (projectId: number) => {
    const target = projects.find((project) => project.id === projectId);
    if (!target) {
      return false;
    }

    // Optimistically update
    setProjects((prev) =>
      prev.map((project) => ({
        ...project,
        is_active: project.id === projectId,
        is_selected: project.id === projectId ? true : project.is_selected,
      }))
    );

    const result = await api.put<Project>(`/projects/${projectId}/selection`, {
      is_active: true,
      is_selected: true,
    });

    if (result.error) {
      await refreshProjects();
      return false;
    }

    return true;
  }, [projects, refreshProjects]);

  const toggleProjectSelection = useCallback(async (projectId: number) => {
    const target = projects.find((project) => project.id === projectId);
    if (!target) {
      return false;
    }

    const nextSelected = !target.is_selected;

    // Optimistically update
    setProjects((prev) =>
      prev.map((project) =>
        project.id === projectId ? { ...project, is_selected: nextSelected } : project
      )
    );

    const result = await api.put<Project>(`/projects/${projectId}/selection`, {
      is_active: target.is_active,
      is_selected: nextSelected,
    });

    if (result.error) {
      await refreshProjects();
      return false;
    }

    return true;
  }, [projects, refreshProjects]);

  const value = useMemo<ProjectContextType>(() => ({
    projects,
    activeProject,
    selectedProjects,
    loading,
    syncing,
    refreshProjects,
    syncProjects,
    setActiveProject,
    toggleProjectSelection,
  }), [projects, activeProject, selectedProjects, loading, syncing, refreshProjects, syncProjects, setActiveProject, toggleProjectSelection]);

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProjects() {
  const context = useContext(ProjectContext);
  if (!context) {
    throw new Error("useProjects must be used within a ProjectProvider");
  }
  return context;
}
