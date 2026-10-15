"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useProjects } from "@/contexts/ProjectContext";
import { api } from "@/services/api";

interface Story {
  id: string;
  title: string;
  status: string;
  priority: string;
  story_points: number;
  project_id: string;
}

export default function MyStoriesWidget({ developerId = "dev-1" }: { developerId?: string }) {
  const { projects: userProjects, activeProject } = useProjects();
  const [stories, setStories] = useState<Story[]>([]);
  const [loading, setLoading] = useState(true);

  const projectIds = useMemo(() => {
    const list = userProjects
      .map((project) => project.jira_project_key)
      .filter((value): value is string => Boolean(value));
    if (list.length > 0) return list;
    if (activeProject?.jira_project_key) return [activeProject.jira_project_key];
    return [];
  }, [userProjects, activeProject]);

  const loadData = useCallback(async () => {
    setLoading(true);
    const allStories: Story[] = [];
    for (const proj of projectIds) {
      const result = await api.get<{ stories: Story[] }>(
        `/proxy/jira/projects/${proj}/stories?assignee=${developerId}`
      );
      // Guard against error bodies lacking a `stories` array so the widget
      // never throws and strands in "Loading...".
      const list = result.data?.stories;
      if (Array.isArray(list)) {
        allStories.push(...list.filter((s) => s.status !== "done"));
      }
    }
    setStories(allStories);
    setLoading(false);
  }, [developerId, projectIds]);

  useEffect(() => {
    // Defer to a microtask so the synchronous setLoading(true) at the top of
    // loadData doesn't run in the effect body (react-hooks/set-state-in-effect).
    queueMicrotask(loadData);
  }, [loadData]);

  if (loading) return <div className="text-sm text-gray-400">Loading...</div>;
  if (stories.length === 0) return <div className="text-sm text-gray-500">No active stories assigned</div>;

  const priorityColors: Record<string, string> = {
    critical: "text-red-600 bg-red-50",
    high: "text-orange-600 bg-orange-50",
    medium: "text-blue-600 bg-blue-50",
    low: "text-gray-600 bg-gray-50",
  };

  const statusIcons: Record<string, string> = {
    todo: "⬜",
    in_progress: "🔵",
    in_review: "🟡",
  };

  return (
    <div className="space-y-2">
      {stories.map((story) => (
        <div key={story.id} className="flex items-center gap-2 p-2 rounded hover:bg-gray-50 transition-colors">
          <span className="text-sm">{statusIcons[story.status] || "⬜"}</span>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-gray-800 truncate">{story.id}: {story.title}</p>
            <p className="text-[10px] text-gray-400">{story.project_id} • {story.story_points}pts</p>
          </div>
          <span className={`text-[10px] px-1.5 py-0.5 rounded ${priorityColors[story.priority] || "bg-gray-50"}`}>
            {story.priority}
          </span>
        </div>
      ))}
    </div>
  );
}
