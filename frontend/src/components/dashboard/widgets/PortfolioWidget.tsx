"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/services/api";

interface Project {
  id: string;
  name: string;
}

interface ProjectHealth {
  id: string;
  name: string;
  health: "green" | "yellow" | "red";
  activeStories: number;
  blockers: number;
  openPRs: number;
}

export default function PortfolioWidget({ selectedProjects = [] }: { selectedProjects?: Array<{ jira_project_key: string | null; name: string }> }) {
  const [projects, setProjects] = useState<ProjectHealth[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    const projResult = await api.get<{ projects: Project[] }>("/proxy/jira/projects");
    if (projResult.data) {
      const selectedJiraKeys = selectedProjects
        .map((project) => project.jira_project_key)
        .filter((value): value is string => Boolean(value));

      const filteredProjects = selectedJiraKeys.length > 0
        ? projResult.data.projects.filter((proj) => selectedJiraKeys.includes(proj.id))
        : projResult.data.projects;

      const healthData: ProjectHealth[] = [];
      const repoMap: Record<string, string> = {
        PAY: "repo-1", CART: "repo-2", AUTH: "repo-3", PROD: "repo-4", ORD: "repo-5",
      };

      for (const proj of filteredProjects) {
        const stories = await api.get<{ stories: Array<{ status: string; priority: string }> }>(
          `/proxy/jira/projects/${proj.id}/stories`
        );
        const repoId = repoMap[proj.id];
        const prs = repoId
          ? await api.get<{ pull_requests: Array<{ status: string }> }>(`/proxy/github/repos/${repoId}/pulls`)
          : null;

        const storyList = stories.data?.stories || [];
        const blockers = storyList.filter((s) => s.priority === "critical" && s.status !== "done").length;
        const active = storyList.filter((s) => s.status === "in_progress" || s.status === "in_review").length;
        const openPRs = prs?.data?.pull_requests.filter((p) => p.status === "open").length || 0;

        let health: "green" | "yellow" | "red" = "green";
        if (blockers > 0) health = "red";
        else if (active === 0) health = "yellow";

        healthData.push({
          id: proj.id,
          name: proj.name,
          health,
          activeStories: active,
          blockers,
          openPRs,
        });
      }
      setProjects(healthData);
    }
    setLoading(false);
  }, [selectedProjects]);

  useEffect(() => {
    // Defer to a microtask so the synchronous setLoading(true) at the top of
    // loadData doesn't run in the effect body (react-hooks/set-state-in-effect).
    queueMicrotask(loadData);
  }, [loadData]);

  if (loading) return <div className="text-sm text-gray-400">Loading...</div>;

  const healthColors = {
    green: "bg-green-500",
    yellow: "bg-yellow-500",
    red: "bg-red-500",
  };

  return (
    <div className="space-y-3">
      {projects.map((proj) => (
        <div key={proj.id} className="flex items-center gap-3 p-2 rounded hover:bg-gray-50">
          <div className={`w-3 h-3 rounded-full ${healthColors[proj.health]}`} />
          <div className="flex-1">
            <p className="text-xs font-medium text-gray-800">{proj.name}</p>
            <p className="text-[10px] text-gray-400">
              {proj.activeStories} active • {proj.openPRs} PRs • {proj.blockers} blockers
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
