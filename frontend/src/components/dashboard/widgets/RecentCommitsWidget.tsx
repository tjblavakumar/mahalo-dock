"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useProjects } from "@/contexts/ProjectContext";
import { api } from "@/services/api";

interface Commit {
  id: string;
  message: string;
  author: string;
  date: string;
  additions: number;
  deletions: number;
  repo_id: string;
}

export default function RecentCommitsWidget({ developerId = "dev-1" }: { developerId?: string }) {
  const { projects: userProjects, activeProject } = useProjects();
  const [commits, setCommits] = useState<Commit[]>([]);
  const [loading, setLoading] = useState(true);

  // Use the REAL repo names mapped to the user's projects (e.g. payment-service),
  // not hardcoded ids like repo-1..repo-5 which do not exist in the Gitea backend.
  const repoIds = useMemo(() => {
    const list = userProjects
      .map((project) => project.github_repo_name)
      .filter((value): value is string => Boolean(value));
    if (list.length > 0) return Array.from(new Set(list));
    if (activeProject?.github_repo_name) return [activeProject.github_repo_name];
    return [];
  }, [userProjects, activeProject]);

  const loadData = useCallback(async () => {
    setLoading(true);
    const allCommits: Commit[] = [];
    for (const repo of repoIds) {
      const result = await api.get<{ commits: Commit[] }>(
        `/proxy/github/repos/${repo}/commits?author=${developerId}`
      );
      // Guard against error/404 bodies that lack a `commits` array, so a bad
      // repo can never throw and strand the widget in "Loading..." forever.
      const list = result.data?.commits;
      if (Array.isArray(list)) {
        allCommits.push(...list.map((c) => ({ ...c, repo_id: repo })));
      }
    }
    allCommits.sort((a, b) => b.date.localeCompare(a.date));
    setCommits(allCommits.slice(0, 10));
    setLoading(false);
  }, [developerId, repoIds]);

  useEffect(() => {
    // Defer to a microtask so the synchronous setLoading(true) at the top of
    // loadData doesn't run in the effect body (react-hooks/set-state-in-effect).
    queueMicrotask(loadData);
  }, [loadData]);

  if (loading) return <div className="text-sm text-gray-400">Loading...</div>;
  if (commits.length === 0) return <div className="text-sm text-gray-500">No recent commits</div>;

  return (
    <div className="space-y-1.5">
      {commits.map((commit) => (
        <div key={commit.id} className="flex items-start gap-2 py-1">
          <div className="w-1.5 h-1.5 bg-blue-400 rounded-full mt-1.5 shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="text-xs text-gray-800 truncate">{commit.message}</p>
            <p className="text-[10px] text-gray-400">
              {commit.date} • +{commit.additions}/-{commit.deletions}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
