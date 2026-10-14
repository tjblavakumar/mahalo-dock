"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Project } from "@/types";

interface ProjectMultiSelectProps {
  projects: Project[];
  /** Toggles a single project's selection. Returns success. */
  onToggle: (projectId: number) => Promise<boolean> | void;
  /** Selects or clears every project at once. Optional. */
  onToggleAll?: (select: boolean) => Promise<void> | void;
}

/**
 * A compact multi-select dropdown for choosing which projects are included in
 * the dashboard/chat scope. Styled for the dark sidebar. Selection state is
 * derived from each project's `is_selected` flag (owned by ProjectContext), so
 * the control stays in sync with every other consumer.
 */
export default function ProjectMultiSelect({
  projects,
  onToggle,
  onToggleAll,
}: ProjectMultiSelectProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const selected = useMemo(
    () => projects.filter((p) => p.is_selected),
    [projects]
  );
  const allSelected = projects.length > 0 && selected.length === projects.length;

  // Close on outside click and on Escape.
  useEffect(() => {
    if (!open) return;

    function onPointerDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Summary label shown on the trigger button.
  const summary =
    selected.length === 0
      ? "All projects"
      : selected.length === 1
        ? selected[0].name
        : `${selected.length} projects selected`;

  async function handleToggleAll() {
    if (onToggleAll) {
      await onToggleAll(!allSelected);
      return;
    }
    // Fallback: toggle each project individually toward the target state.
    const target = !allSelected;
    for (const p of projects) {
      if (p.is_selected !== target) {
        await onToggle(p.id);
      }
    }
  }

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="w-full flex items-center justify-between gap-2 rounded-lg border border-gray-700 bg-gray-800/80 px-3 py-2 text-left text-xs text-gray-200 hover:bg-gray-800 transition-colors"
      >
        <span className="truncate">{summary}</span>
        <svg
          className={`h-3.5 w-3.5 shrink-0 text-gray-400 transition-transform ${open ? "rotate-180" : ""}`}
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 11.17l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {open && (
        <div
          role="listbox"
          aria-multiselectable="true"
          className="absolute bottom-full left-0 z-20 mb-1 w-full overflow-hidden rounded-lg border border-gray-700 bg-gray-800 shadow-xl"
        >
          {/* Select all / clear */}
          <button
            type="button"
            onClick={handleToggleAll}
            className="flex w-full items-center gap-2.5 border-b border-gray-700 px-3 py-2 text-left text-xs text-gray-300 hover:bg-gray-700/70 transition-colors"
          >
            <span className="flex h-4 w-4 items-center justify-center rounded border border-gray-500 text-[10px]">
              {allSelected ? "✓" : ""}
            </span>
            <span className="font-medium">
              {allSelected ? "Clear all" : "Select all"}
            </span>
          </button>

          <div className="max-h-60 overflow-y-auto py-1">
            {projects.map((project) => (
              <label
                key={project.id}
                className={`flex cursor-pointer select-none items-center gap-2.5 px-3 py-2 text-xs transition-colors ${
                  project.is_selected
                    ? "text-white"
                    : "text-gray-400 hover:text-gray-200"
                } hover:bg-gray-700/60`}
              >
                <input
                  type="checkbox"
                  checked={project.is_selected}
                  onChange={() => {
                    void onToggle(project.id);
                  }}
                  className="h-4 w-4 rounded accent-blue-500 cursor-pointer"
                />
                <span className="truncate">{project.name}</span>
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
