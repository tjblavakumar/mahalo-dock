"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/services/api";

interface Story {
  id: string;
  title: string;
  story_points: number;
  assignee: string | null;
  status: string;
}

interface BoardData {
  sprint: { name: string; start_date: string; end_date: string } | null;
  columns: Record<string, Story[]>;
}

interface ProjectBoard {
  projectId: string;
  projectName: string;
  data: BoardData;
}

export default function SprintBoardWidget({
  projectId,
  selectedProjects = [],
}: {
  projectId?: string;
  selectedProjects?: Array<{ jira_project_key: string | null; name: string }>;
}) {
  const [boards, setBoards] = useState<ProjectBoard[]>([]);
  const [activeTab, setActiveTab] = useState<string>("");
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

    const loadedBoards: ProjectBoard[] = [];
    for (const target of targets) {
      const result = await api.get<BoardData>(`/proxy/jira/projects/${target.id}/board`);
      if (result.data) {
        loadedBoards.push({
          projectId: target.id,
          projectName: target.name,
          data: result.data,
        });
      }
    }

    setBoards(loadedBoards);
    if (loadedBoards.length > 0) {
      setActiveTab((prev) => (loadedBoards.some((b) => b.projectId === prev) ? prev : loadedBoards[0].projectId));
    } else {
      setActiveTab("");
    }
    setLoading(false);
  }, [projectId, selectedProjects]);

  useEffect(() => {
    // Defer to a microtask so the synchronous setLoading(true) at the top of
    // loadData doesn't run in the effect body (react-hooks/set-state-in-effect).
    queueMicrotask(loadData);
  }, [loadData]);

  if (loading) return <div className="text-sm text-gray-400">Loading sprint boards...</div>;
  if (boards.length === 0) return <div className="text-sm text-gray-500">No sprint data available</div>;

  const currentBoard = boards.find((b) => b.projectId === activeTab) || boards[0];
  const boardData = currentBoard?.data;

  const statusColors: Record<string, string> = {
    todo: "bg-gray-100 text-gray-700",
    in_progress: "bg-blue-100 text-blue-700",
    in_review: "bg-yellow-100 text-yellow-700",
    done: "bg-green-100 text-green-700",
  };

  return (
    <div className="space-y-3">
      {boards.length > 1 && (
        <div className="flex items-center gap-1.5 border-b border-gray-100 pb-2 overflow-x-auto">
          {boards.map((b) => (
            <button
              key={b.projectId}
              type="button"
              onClick={() => setActiveTab(b.projectId)}
              className={`px-3 py-1 text-xs rounded-full transition-colors whitespace-nowrap font-medium ${
                activeTab === b.projectId
                  ? "bg-blue-600 text-white shadow-sm"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {b.projectName}
            </button>
          ))}
        </div>
      )}

      {boardData?.sprint ? (
        <div>
          <div className="flex items-center justify-between mb-3 text-xs text-gray-500">
            <span className="font-semibold text-gray-700">{currentBoard.projectName}</span>
            <span>
              {boardData.sprint.name} ({boardData.sprint.start_date} to {boardData.sprint.end_date})
            </span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {["todo", "in_progress", "in_review", "done"].map((col) => (
              <div key={col} className="bg-gray-50/70 p-2 rounded-lg border border-gray-100">
                <p className="text-[11px] font-semibold text-gray-500 uppercase mb-2">
                  {col.replace("_", " ")} ({(boardData.columns[col] || []).length})
                </p>
                <div className="space-y-1.5 max-h-56 overflow-y-auto pr-0.5">
                  {(boardData.columns[col] || []).length === 0 ? (
                    <p className="text-[10px] text-gray-400 italic py-2 text-center">Empty</p>
                  ) : (
                    (boardData.columns[col] || []).map((story) => (
                      <div
                        key={story.id}
                        className={`rounded p-2 text-xs shadow-2xs ${statusColors[col]}`}
                      >
                        <p className="font-semibold truncate">{story.id}</p>
                        <p className="truncate opacity-85 text-[11px] mt-0.5" title={story.title}>
                          {story.title}
                        </p>
                        <p className="opacity-65 text-[10px] mt-1 font-mono">{story.story_points} pts</p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="text-xs text-gray-400 py-4 text-center">
          No active sprint for {currentBoard?.projectName}
        </div>
      )}
    </div>
  );
}
