"use client";

import { useCallback, useEffect, useState } from "react";
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
  const [commits, setCommits] = useState<Commit[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    const repos = ["repo-1", "repo-2", "repo-3", "repo-4", "repo-5"];
    const allCommits: Commit[] = [];
    for (const repo of repos) {
      const result = await api.get<{ commits: Commit[] }>(
        `/proxy/github/repos/${repo}/commits?author=${developerId}`
      );
      if (result.data) {
        allCommits.push(...result.data.commits.map((c) => ({ ...c, repo_id: repo })));
      }
    }
    allCommits.sort((a, b) => b.date.localeCompare(a.date));
    setCommits(allCommits.slice(0, 10));
    setLoading(false);
  }, [developerId]);

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
