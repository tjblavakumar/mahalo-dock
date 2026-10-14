"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/services/api";

interface Sprint {
  id: string;
  name: string;
  status: string;
  velocity: number | null;
  completed_points?: number;
  total_points?: number;
}

interface ProjectVelocity {
  projectId: string;
  projectName: string;
  sprints: Sprint[];
  avgVelocity: number;
}

export default function VelocityWidget({
  projectId,
  selectedProjects = [],
}: {
  projectId?: string;
  selectedProjects?: Array<{ jira_project_key: string | null; name: string }>;
}) {
  const [projectVelocities, setProjectVelocities] = useState<ProjectVelocity[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);

    let targets: Array<{ id: string; name: string }> = [];

    if (selectedProjects.length > 0) {
      targets = selectedProjects
        .filter((p) => Boolean(p.jira_project_key))
        .map((p) => ({ id: p.jira_project_key!, name: p.name }));
    } else if (projectId) {
      targets = [{ id: projectId, name: projectId }];
    } else {
      const projResult = await api.get<{ projects: Array<{ id: string; name: string }> }>("/proxy/jira/projects");
      if (projResult.data) {
        targets = projResult.data.projects.map((p) => ({ id: p.id, name: p.name }));
      }
    }

    const list: ProjectVelocity[] = [];
    for (const target of targets) {
      const result = await api.get<{ sprints: Sprint[] }>(`/proxy/jira/sprints/${target.id}`);
      const sprints = result.data?.sprints || [];
      const completedSprints = sprints.filter((s) => s.status === "completed" && s.velocity);
      const avgVelocity = completedSprints.length > 0
        ? Math.round(completedSprints.reduce((sum, s) => sum + (s.velocity || 0), 0) / completedSprints.length)
        : 0;

      list.push({
        projectId: target.id,
        projectName: target.name,
        sprints,
        avgVelocity,
      });
    }

    setProjectVelocities(list);
    setLoading(false);
  }, [projectId, selectedProjects]);

  useEffect(() => {
    // Defer to a microtask so the synchronous setLoading(true) at the top of
    // loadData doesn't run in the effect body (react-hooks/set-state-in-effect).
    queueMicrotask(loadData);
  }, [loadData]);

  if (loading) return <div className="text-sm text-gray-400">Loading...</div>;
  if (projectVelocities.length === 0) return <div className="text-sm text-gray-500">No sprint data found</div>;

  const totalAvgVelocity = Math.round(
    projectVelocities.reduce((sum, pv) => sum + pv.avgVelocity, 0) / (projectVelocities.length || 1)
  );

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div className="flex items-baseline gap-2">
          <span className="text-3xl font-bold text-gray-900">{totalAvgVelocity}</span>
          <span className="text-xs text-gray-500">
            {projectVelocities.length > 1 ? "avg pts/sprint across selected" : "avg pts/sprint"}
          </span>
        </div>
        {projectVelocities.length > 1 && (
          <span className="text-xs text-blue-600 font-medium">
            {projectVelocities.length} projects
          </span>
        )}
      </div>

      <div className="space-y-4 max-h-64 overflow-y-auto pr-1">
        {projectVelocities.map((pv) => (
          <div key={pv.projectId} className="rounded-lg border border-gray-100 bg-gray-50/60 p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-800 truncate" title={pv.projectName}>
                {pv.projectName}
              </span>
              <span className="text-[11px] font-medium text-gray-600 bg-white px-2 py-0.5 rounded border border-gray-200">
                {pv.avgVelocity} pts avg
              </span>
            </div>

            <div className="space-y-1.5">
              {pv.sprints.length === 0 ? (
                <p className="text-[11px] text-gray-400 italic">No sprints recorded</p>
              ) : (
                pv.sprints.map((sprint) => (
                  <div key={sprint.id} className="flex items-center gap-2">
                    <span className="text-[11px] text-gray-500 w-24 truncate" title={sprint.name}>
                      {sprint.name}
                    </span>
                    <div className="flex-1 bg-gray-200/80 rounded-full h-3.5">
                      {sprint.velocity && (
                        <div
                          className="bg-blue-500 rounded-full h-3.5 flex items-center justify-end pr-1.5"
                          style={{ width: `${Math.min(100, (sprint.velocity / 40) * 100)}%` }}
                        >
                          <span className="text-[9px] text-white font-medium">
                            {sprint.velocity}
                          </span>
                        </div>
                      )}
                      {sprint.status === "active" && sprint.completed_points !== undefined && (
                        <div
                          className="bg-green-500 rounded-full h-3.5 flex items-center justify-end pr-1.5"
                          style={{ width: `${Math.min(100, ((sprint.completed_points || 0) / (sprint.total_points || 1)) * 100)}%` }}
                        >
                          <span className="text-[9px] text-white font-medium">
                            {sprint.completed_points}/{sprint.total_points}
                          </span>
                        </div>
                      )}
                    </div>
                    <span className={`text-[10px] px-1.5 py-0.2 rounded font-medium ${
                      sprint.status === "completed" ? "bg-green-100 text-green-700" :
                      sprint.status === "active" ? "bg-blue-100 text-blue-700" :
                      "bg-gray-100 text-gray-600"
                    }`}>
                      {sprint.status}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
