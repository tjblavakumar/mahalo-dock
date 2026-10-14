"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/services/api";

interface Metrics {
  totalStories: number;
  storiesCompleted: number;
  openPRs: number;
  totalCommits: number;
  byProject: Array<{
    name: string;
    storiesCompleted: number;
    totalStories: number;
    openPRs: number;
    totalCommits: number;
  }>;
}

export default function KeyMetricsWidget({
  selectedProjects = [],
}: {
  selectedProjects?: Array<{
    name: string;
    jira_project_key: string | null;
    github_repo_name: string | null;
  }>;
}) {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);

    const repoMap: Record<string, string> = {
      PAY: "repo-1",
      CART: "repo-2",
      AUTH: "repo-3",
      PROD: "repo-4",
      ORD: "repo-5",
    };

    let targetProjects: Array<{
      name: string;
      jiraKey: string;
      repoName: string;
    }> = [];

    if (selectedProjects.length > 0) {
      targetProjects = selectedProjects.map((p) => ({
        name: p.name,
        jiraKey: p.jira_project_key || "PAY",
        repoName: p.github_repo_name || repoMap[p.jira_project_key || ""] || "repo-1",
      }));
    } else {
      const projResult = await api.get<{ projects: Array<{ id: string; name: string }> }>("/proxy/jira/projects");
      if (projResult.data) {
        targetProjects = projResult.data.projects.map((p) => ({
          name: p.name,
          jiraKey: p.id,
          repoName: repoMap[p.id] || "repo-1",
        }));
      }
    }

    let totalStories = 0;
    let storiesCompleted = 0;
    let openPRs = 0;
    let totalCommits = 0;
    const byProjectList: Metrics["byProject"] = [];

    for (const proj of targetProjects) {
      let pStoriesTotal = 0;
      let pStoriesDone = 0;
      let pOpenPRs = 0;
      let pCommits = 0;

      const result = await api.get<{ stories: Array<{ status: string }> }>(
        `/proxy/jira/projects/${proj.jiraKey}/stories`
      );
      if (result.data) {
        pStoriesTotal = result.data.stories.length;
        pStoriesDone = result.data.stories.filter((s) => s.status === "done").length;
        totalStories += pStoriesTotal;
        storiesCompleted += pStoriesDone;
      }

      const prResult = await api.get<{ pull_requests: Array<{ status: string }> }>(
        `/proxy/github/repos/${proj.repoName}/pulls`
      );
      if (prResult.data) {
        pOpenPRs = prResult.data.pull_requests.filter((p) => p.status === "open").length;
        openPRs += pOpenPRs;
      }

      const statsResult = await api.get<{ total_commits: number }>(
        `/proxy/github/repos/${proj.repoName}/stats`
      );
      if (statsResult.data) {
        pCommits = statsResult.data.total_commits;
        totalCommits += pCommits;
      }

      byProjectList.push({
        name: proj.name,
        storiesCompleted: pStoriesDone,
        totalStories: pStoriesTotal,
        openPRs: pOpenPRs,
        totalCommits: pCommits,
      });
    }

    setMetrics({
      totalStories,
      storiesCompleted,
      openPRs,
      totalCommits,
      byProject: byProjectList,
    });
    setLoading(false);
  }, [selectedProjects]);

  useEffect(() => {
    // Defer to a microtask so the synchronous setLoading(true) at the top of
    // loadData doesn't run in the effect body (react-hooks/set-state-in-effect).
    queueMicrotask(loadData);
  }, [loadData]);

  if (loading) return <div className="text-sm text-gray-400">Loading...</div>;
  if (!metrics) return null;

  const items = [
    { label: "Stories Completed", value: metrics.storiesCompleted, total: metrics.totalStories, color: "text-green-600" },
    { label: "Open PRs", value: metrics.openPRs, color: "text-blue-600" },
    { label: "Total Commits", value: metrics.totalCommits, color: "text-purple-600" },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        {items.map((item) => (
          <div key={item.label} className="text-center p-2 rounded-lg bg-gray-50 border border-gray-100">
            <p className={`text-xl font-bold ${item.color}`}>
              {item.value}
              {item.total !== undefined && item.total > 0 && (
                <span className="text-xs text-gray-400">/{item.total}</span>
              )}
            </p>
            <p className="text-[10px] text-gray-500 mt-0.5">{item.label}</p>
          </div>
        ))}
      </div>

      {metrics.byProject.length > 1 && (
        <div className="pt-2 border-t border-gray-100 space-y-2">
          <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
            Breakdown by project
          </p>
          <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
            {metrics.byProject.map((bp) => (
              <div key={bp.name} className="flex items-center justify-between text-xs py-1 px-2 rounded bg-gray-50/70 border border-gray-100">
                <span className="font-medium text-gray-700 truncate max-w-[120px]" title={bp.name}>
                  {bp.name}
                </span>
                <span className="text-[11px] text-gray-500 flex gap-2">
                  <span className="text-green-700 font-medium">{bp.storiesCompleted}/{bp.totalStories} done</span>
                  <span>•</span>
                  <span className="text-blue-700">{bp.openPRs} PRs</span>
                  <span>•</span>
                  <span className="text-purple-700">{bp.totalCommits} commits</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
