"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useProjects } from "@/contexts/ProjectContext";
import { api } from "@/services/api";

interface PullRequest {
  id: string;
  number: number;
  title: string;
  status: string;
  repo_id: string;
  additions: number;
  deletions: number;
  linked_story: string;
}

export default function MyPRsWidget({ developerId = "dev-1" }: { developerId?: string }) {
  const { projects: userProjects, activeProject } = useProjects();
  const [prs, setPRs] = useState<PullRequest[]>([]);
  const [loading, setLoading] = useState(true);

  const repoIds = useMemo(() => {
    const list = userProjects
      .map((project) => project.github_repo_name)
      .filter((value): value is string => Boolean(value));
    if (list.length > 0) return list;
    if (activeProject?.github_repo_name) return [activeProject.github_repo_name];
    return [];
  }, [userProjects, activeProject]);

  const loadData = useCallback(async () => {
    setLoading(true);
    const allPRs: PullRequest[] = [];
    for (const repo of repoIds) {
      const result = await api.get<{ pull_requests: PullRequest[] }>(
        `/proxy/github/repos/${repo}/pulls?author_id=${developerId}`
      );
      if (result.data) {
        allPRs.push(...result.data.pull_requests);
      }
    }
    setPRs(allPRs);
    setLoading(false);
  }, [developerId, repoIds]);

  useEffect(() => {
    // Defer to a microtask so the synchronous setLoading(true) at the top of
    // loadData doesn't run in the effect body (react-hooks/set-state-in-effect).
    queueMicrotask(loadData);
  }, [loadData]);

  if (loading) return <div className="text-sm text-gray-400">Loading...</div>;
  if (prs.length === 0) return <div className="text-sm text-gray-500">No open pull requests</div>;

  const statusColors: Record<string, string> = {
    open: "bg-green-100 text-green-700",
    draft: "bg-gray-100 text-gray-600",
    merged: "bg-purple-100 text-purple-700",
  };

  return (
    <div className="space-y-2">
      {prs.map((pr) => (
        <div key={pr.id} className="p-2 rounded hover:bg-gray-50 transition-colors">
          <div className="flex items-center gap-2">
            <span className="text-sm">🔀</span>
            <p className="text-xs font-medium text-gray-800 truncate flex-1">
              #{pr.number} {pr.title}
            </p>
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${statusColors[pr.status] || "bg-gray-100"}`}>
              {pr.status}
            </span>
          </div>
          <p className="text-[10px] text-gray-400 ml-6">
            +{pr.additions}/-{pr.deletions} • {pr.linked_story || "no linked story"}
          </p>
        </div>
      ))}
    </div>
  );
}
