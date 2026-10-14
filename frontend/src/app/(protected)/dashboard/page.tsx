"use client";

import { useMemo } from "react";
import type { Layout } from "react-grid-layout";
import { useAuth } from "@/contexts/AuthContext";
import { useProjects } from "@/contexts/ProjectContext";
import { useRequiredConnections } from "@/hooks/useRequiredConnections";
import DashboardGrid, { type DashboardWidget } from "@/components/dashboard/DashboardGrid";
import SprintBoardWidget from "@/components/dashboard/widgets/SprintBoardWidget";
import VelocityWidget from "@/components/dashboard/widgets/VelocityWidget";
import ProjectStatusWidget from "@/components/dashboard/widgets/ProjectStatusWidget";
import PortfolioWidget from "@/components/dashboard/widgets/PortfolioWidget";
import KeyMetricsWidget from "@/components/dashboard/widgets/KeyMetricsWidget";
import MyStoriesWidget from "@/components/dashboard/widgets/MyStoriesWidget";
import MyPRsWidget from "@/components/dashboard/widgets/MyPRsWidget";
import RecentCommitsWidget from "@/components/dashboard/widgets/RecentCommitsWidget";

import type { Project } from "@/types";

const ROLE_LABELS: Record<string, string> = {
  product_manager: "Product Manager",
  developer: "Developer",
  executive: "Executive",
};

interface RoleDashboard {
  widgets: DashboardWidget[];
  layout: Layout[];
}

function buildRoleDashboard(role: string | undefined, selectedProjects: Project[]): RoleDashboard {
  if (role === "product_manager") {
    return {
      widgets: [
        { id: "sprint-board", title: "Sprint Board", content: <SprintBoardWidget selectedProjects={selectedProjects} /> },
        { id: "velocity", title: "Sprint Velocity", content: <VelocityWidget selectedProjects={selectedProjects} /> },
        { id: "project-status", title: "Project Status", content: <ProjectStatusWidget selectedProjects={selectedProjects} /> },
        { id: "key-metrics", title: "Key Metrics", content: <KeyMetricsWidget selectedProjects={selectedProjects} /> },
      ],
      layout: [
        { i: "sprint-board", x: 0, y: 0, w: 8, h: 4, minW: 4, minH: 3 },
        { i: "velocity", x: 8, y: 0, w: 4, h: 4, minW: 3, minH: 3 },
        { i: "project-status", x: 0, y: 4, w: 8, h: 4, minW: 4, minH: 3 },
        { i: "key-metrics", x: 8, y: 4, w: 4, h: 4, minW: 3, minH: 3 },
      ],
    };
  }

  if (role === "executive") {
    return {
      widgets: [
        { id: "portfolio", title: "Portfolio Health", content: <PortfolioWidget selectedProjects={selectedProjects} /> },
        { id: "key-metrics", title: "Key Metrics", content: <KeyMetricsWidget selectedProjects={selectedProjects} /> },
        { id: "velocity", title: "Sprint Velocity", content: <VelocityWidget selectedProjects={selectedProjects} /> },
        { id: "project-status", title: "Project Completion", content: <ProjectStatusWidget selectedProjects={selectedProjects} /> },
        { id: "sprint-board", title: "Sprint Board Overview", content: <SprintBoardWidget selectedProjects={selectedProjects} /> },
      ],
      layout: [
        { i: "portfolio", x: 0, y: 0, w: 4, h: 4, minW: 3, minH: 3 },
        { i: "key-metrics", x: 4, y: 0, w: 4, h: 4, minW: 3, minH: 3 },
        { i: "velocity", x: 8, y: 0, w: 4, h: 4, minW: 3, minH: 3 },
        { i: "project-status", x: 0, y: 4, w: 8, h: 4, minW: 4, minH: 3 },
        { i: "sprint-board", x: 0, y: 8, w: 8, h: 4, minW: 4, minH: 3 },
      ],
    };
  }

  if (role === "developer") {
    return {
      widgets: [
        { id: "my-stories", title: "My Stories", content: <MyStoriesWidget developerId="dev-1" /> },
        { id: "my-prs", title: "My Pull Requests", content: <MyPRsWidget developerId="dev-1" /> },
        { id: "recent-commits", title: "Recent Commits", content: <RecentCommitsWidget developerId="dev-1" /> },
        { id: "sprint-board", title: "Sprint Board", content: <SprintBoardWidget selectedProjects={selectedProjects} /> },
        { id: "velocity", title: "Sprint Velocity", content: <VelocityWidget selectedProjects={selectedProjects} /> },
      ],
      layout: [
        { i: "my-stories", x: 0, y: 0, w: 4, h: 4, minW: 3, minH: 3 },
        { i: "my-prs", x: 4, y: 0, w: 4, h: 4, minW: 3, minH: 3 },
        { i: "recent-commits", x: 8, y: 0, w: 4, h: 4, minW: 3, minH: 3 },
        { i: "sprint-board", x: 0, y: 4, w: 8, h: 4, minW: 4, minH: 3 },
        { i: "velocity", x: 8, y: 4, w: 4, h: 4, minW: 3, minH: 3 },
      ],
    };
  }

  return { widgets: [], layout: [] };
}

export default function DashboardPage() {
  const { user } = useAuth();
  const { selectedProjects, loading: projectsLoading } = useProjects();
  const { isConfigured, loading: connectionsLoading } = useRequiredConnections();

  const { widgets, layout } = useMemo(
    () => buildRoleDashboard(user?.role, selectedProjects),
    [user?.role, selectedProjects]
  );

  // Data is still settling until both connections and projects have loaded.
  // We hold back the project banner and widgets until then so transient states
  // like "No projects selected (showing all)" never flash during load.
  const isInitializing = connectionsLoading || projectsLoading;

  if (isInitializing) {
    return (
      <div className="p-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-gray-600 mt-1">
            Welcome back, {user?.name}!{" "}
            <span className="text-blue-600 font-medium">
              {user ? ROLE_LABELS[user.role] || user.role : ""}
            </span>{" "}
            view
          </p>
        </div>
        <div className="flex items-center gap-2 text-gray-500">
          <div className="w-4 h-4 border-2 border-gray-300 border-t-blue-500 rounded-full animate-spin" />
          <span>Loading your dashboard...</span>
        </div>
      </div>
    );
  }

  if (!isConfigured) {
    return (
      <div className="p-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-gray-600 mt-1">
            Welcome back, {user?.name}!{" "}
            <span className="text-blue-600 font-medium">
              {user ? ROLE_LABELS[user.role] || user.role : ""}
            </span>{" "}
            view
          </p>
        </div>
        <div className="bg-white rounded-lg shadow p-12 text-center">
          <p className="text-4xl mb-4">📊</p>
          <p className="text-gray-500 mb-2">No connections configured yet.</p>
          <p className="text-gray-400 text-sm">
            Configure{" "}
            <a href="/connections" className="text-blue-600 hover:underline font-medium">
              Jira, Confluence, and GitHub
            </a>{" "}
            on the Connections page to view your dashboard.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-8 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-gray-600 mt-1">
            Welcome back, {user?.name}!{" "}
            <span className="text-blue-600 font-medium">
              {user ? ROLE_LABELS[user.role] || user.role : ""}
            </span>{" "}
            view
          </p>
        </div>

        <div className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800">
          {selectedProjects.length === 0 ? (
            <span className="text-gray-500">No projects selected (showing all)</span>
          ) : selectedProjects.length === 1 ? (
            <span>Project: <strong className="font-semibold">{selectedProjects[0].name}</strong></span>
          ) : (
            <span>Aggregating <strong className="font-semibold">{selectedProjects.length}</strong> selected projects</span>
          )}
        </div>
      </div>

      {widgets.length > 0 ? (
        <DashboardGrid
          widgets={widgets}
          defaultLayout={layout}
          storageKey={`${user?.id ?? "anon"}:${user?.role ?? "none"}`}
        />
      ) : (
        <div className="bg-white rounded-lg shadow p-12 text-center">
          <p className="text-gray-500">
            {user?.role ? "No widgets available for your role." : "Loading dashboard..."}
          </p>
        </div>
      )}
    </div>
  );
}
