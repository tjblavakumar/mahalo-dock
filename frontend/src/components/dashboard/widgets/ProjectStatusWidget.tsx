"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/services/api";

interface Project {
  id: string;
  name: string;
  status: string;
}

interface StoryData {
  stories: Array<{ status: string; story_points: number }>;
  total: number;
}

interface ProjectStatus {
  id: string;
  name: string;
  total: number;
  done: number;
  inProgress: number;
  percentComplete: number;
}

export default function ProjectStatusWidget({ selectedProjects = [] }: { selectedProjects?: Array<{ jira_project_key: string | null; name: string }> }) {
  const [projects, setProjects] = useState<ProjectStatus[]>([]);
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

      const statuses: ProjectStatus[] = [];
      for (const proj of filteredProjects) {
        const storiesResult = await api.get<StoryData>(`/proxy/jira/projects/${proj.id}/stories`);
        if (storiesResult.data) {
          const stories = storiesResult.data.stories;
          const done = stories.filter((s) => s.status === "done").length;
          const inProg = stories.filter((s) => s.status === "in_progress" || s.status === "in_review").length;
          statuses.push({
            id: proj.id,
            name: proj.name,
            total: stories.length,
            done,
            inProgress: inProg,
            percentComplete: stories.length > 0 ? Math.round((done / stories.length) * 100) : 0,
          });
        }
      }
      setProjects(statuses);
    }
    setLoading(false);
  }, [selectedProjects]);

  useEffect(() => {
    // Defer to a microtask so the synchronous setLoading(true) at the top of
    // loadData doesn't run in the effect body (react-hooks/set-state-in-effect).
    queueMicrotask(loadData);
  }, [loadData]);

  if (loading) return <div className="text-sm text-gray-400">Loading...</div>;

  return (
    <div className="space-y-3">
      {projects.map((proj) => (
        <div key={proj.id}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-medium text-gray-700">{proj.name}</span>
            <span className="text-xs text-gray-500">{proj.percentComplete}%</span>
          </div>
          <div className="w-full bg-gray-100 rounded-full h-2">
            <div
              className="bg-blue-500 rounded-full h-2 transition-all"
              style={{ width: `${proj.percentComplete}%` }}
            />
          </div>
          <p className="text-[10px] text-gray-400 mt-0.5">
            {proj.done} done, {proj.inProgress} in progress, {proj.total - proj.done - proj.inProgress} remaining
          </p>
        </div>
      ))}
    </div>
  );
}
