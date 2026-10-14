"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Responsive,
  WidthProvider,
  type Layout,
  type Layouts,
} from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

const ResponsiveGridLayout = WidthProvider(Responsive);

export interface DashboardWidget {
  /** Stable id used as the grid item key and layout `i`. */
  id: string;
  title: string;
  content: React.ReactNode;
  /** Rendered header actions (optional), shown on the right of the title. */
  headerAction?: React.ReactNode;
}

interface DashboardGridProps {
  widgets: DashboardWidget[];
  /** Default layout for the largest (lg) breakpoint. Smaller breakpoints are derived. */
  defaultLayout: Layout[];
  /** A key that scopes persistence (e.g. `${userId}:${role}`). */
  storageKey: string;
  rowHeight?: number;
}

const BREAKPOINTS = { lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 };
const COLS = { lg: 12, md: 12, sm: 6, xs: 4, xxs: 2 };
const STORAGE_PREFIX = "mahalo3_dashboard_layout";

function loadPersistedLayouts(storageKey: string): Layouts | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(`${STORAGE_PREFIX}:${storageKey}`);
    return raw ? (JSON.parse(raw) as Layouts) : null;
  } catch {
    return null;
  }
}

/**
 * Validates that a persisted layout still matches the current widget set. If
 * widgets were added or removed since the layout was saved, we discard it so
 * the caller's defaults take over (avoids orphaned/missing tiles).
 */
function layoutMatchesWidgets(layout: Layout[] | undefined, widgetIds: string[]): boolean {
  if (!layout) return false;
  const laidOut = new Set(layout.map((item) => item.i));
  return (
    widgetIds.length === laidOut.size &&
    widgetIds.every((id) => laidOut.has(id))
  );
}

export default function DashboardGrid({
  widgets,
  defaultLayout,
  storageKey,
  rowHeight = 80,
}: DashboardGridProps) {
  const widgetIds = useMemo(() => widgets.map((w) => w.id), [widgets]);

  // Build the default multi-breakpoint layouts from the provided lg layout.
  const defaultLayouts = useMemo<Layouts>(
    () => ({
      lg: defaultLayout,
      md: defaultLayout,
      sm: defaultLayout.map((item) => ({ ...item, w: Math.min(item.w, COLS.sm) })),
      xs: defaultLayout.map((item) => ({ ...item, w: COLS.xs, x: 0 })),
      xxs: defaultLayout.map((item) => ({ ...item, w: COLS.xxs, x: 0 })),
    }),
    [defaultLayout]
  );

  // Initialize from localStorage lazily. On the server this returns defaults
  // (loadPersistedLayouts is a no-op without `window`); the client re-computes
  // on mount. Using an initializer instead of an effect avoids a default->saved
  // flash and the set-state-in-effect anti-pattern.
  const [layouts, setLayouts] = useState<Layouts>(() => {
    const persisted = loadPersistedLayouts(storageKey);
    return persisted && layoutMatchesWidgets(persisted.lg, widgetIds)
      ? persisted
      : defaultLayouts;
  });
  const [editing, setEditing] = useState(false);
  const [mounted, setMounted] = useState(false);
  // Gate persistence until after the first mount so we ignore the layout-change
  // event react-grid-layout emits during its initial render. A ref (not state)
  // so onLayoutChange stays stable and doesn't need it as a dependency.
  const readyRef = useRef(false);

  // After mount, reconcile with localStorage (the initializer ran with server
  // values during SSR) and enable CSS transforms. queueMicrotask keeps the
  // setState off the synchronous effect path.
  const lastScopeRef = useRef<string | null>(null);
  useEffect(() => {
    const scopeChanged = lastScopeRef.current !== storageKey;
    lastScopeRef.current = storageKey;
    // Defer so these setState calls don't run synchronously in the effect body
    // (react-hooks/set-state-in-effect).
    queueMicrotask(() => {
      setMounted(true);
      readyRef.current = true;
      if (!scopeChanged) return;
      const persisted = loadPersistedLayouts(storageKey);
      setLayouts(
        persisted && layoutMatchesWidgets(persisted.lg, widgetIds)
          ? persisted
          : defaultLayouts
      );
    });
  }, [storageKey, defaultLayouts, widgetIds]);

  const onLayoutChange = useCallback(
    (_current: Layout[], allLayouts: Layouts) => {
      // Ignore the change react-grid-layout emits before mount.
      if (!readyRef.current) return;
      setLayouts(allLayouts);
      try {
        window.localStorage.setItem(
          `${STORAGE_PREFIX}:${storageKey}`,
          JSON.stringify(allLayouts)
        );
      } catch {
        // Storage may be unavailable (private mode / quota); non-fatal.
      }
    },
    [storageKey]
  );

  const resetLayout = useCallback(() => {
    setLayouts(defaultLayouts);
    try {
      window.localStorage.removeItem(`${STORAGE_PREFIX}:${storageKey}`);
    } catch {
      // non-fatal
    }
  }, [defaultLayouts, storageKey]);

  return (
    <div>
      <div className="mb-3 flex items-center justify-end gap-2">
        {editing && (
          <button
            type="button"
            onClick={resetLayout}
            className="px-3 py-1.5 text-xs font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            Reset layout
          </button>
        )}
        <button
          type="button"
          onClick={() => setEditing((v) => !v)}
          aria-pressed={editing}
          className={`px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
            editing
              ? "bg-blue-600 text-white border-blue-600 hover:bg-blue-700"
              : "text-gray-600 border-gray-200 hover:bg-gray-50"
          }`}
        >
          {editing ? "Done" : "Customize layout"}
        </button>
      </div>

      <ResponsiveGridLayout
        className="layout"
        layouts={layouts}
        breakpoints={BREAKPOINTS}
        cols={COLS}
        rowHeight={rowHeight}
        margin={[24, 24]}
        containerPadding={[0, 0]}
        onLayoutChange={onLayoutChange}
        draggableHandle=".widget-drag-handle"
        isDraggable={editing}
        isResizable={editing}
        useCSSTransforms={mounted}
        compactType="vertical"
      >
        {widgets.map((widget) => (
          <div
            key={widget.id}
            className="bg-white rounded-lg shadow border border-gray-100 overflow-hidden flex flex-col"
          >
            <div
              className={`border-b border-gray-100 px-4 py-2 flex items-center justify-between ${
                editing
                  ? "widget-drag-handle bg-blue-50/60 cursor-move"
                  : "bg-gray-50"
              }`}
            >
              <h3 className="text-sm font-semibold text-gray-700 truncate">
                {widget.title}
              </h3>
              <div className="flex items-center gap-2 shrink-0">
                {widget.headerAction}
                {editing && (
                  <svg
                    className="w-4 h-4 text-gray-400"
                    fill="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path d="M8 6h2v2H8V6zm6 0h2v2h-2V6zM8 11h2v2H8v-2zm6 0h2v2h-2v-2zm-6 5h2v2H8v-2zm6 0h2v2h-2v-2z" />
                  </svg>
                )}
              </div>
            </div>
            <div className="p-4 overflow-auto flex-1">{widget.content}</div>
          </div>
        ))}
      </ResponsiveGridLayout>
    </div>
  );
}
