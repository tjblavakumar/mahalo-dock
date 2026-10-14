"use client";

import { use, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/services/api";
import { useConnections } from "@/contexts/ConnectionsContext";

interface Column {
  key: string;
  label: string;
}

interface TabConfig {
  key: string;
  label: string;
  // Proxy path under /proxy/{type}/... e.g. "stories"
  path: string;
  // Key in the JSON response that holds the array of rows
  dataKey: string;
  columns: Column[];
}

// Per-system tab definitions. Paths map to the mock services' flat list
// endpoints, fetched through the backend proxy: /proxy/{type}/{path}.
const TABS_BY_TYPE: Record<string, TabConfig[]> = {
  jira: [
    {
      key: "stories",
      label: "Stories",
      path: "stories",
      dataKey: "stories",
      columns: [
        { key: "id", label: "ID" },
        { key: "title", label: "Title" },
        { key: "status", label: "Status" },
        { key: "priority", label: "Priority" },
        { key: "story_points", label: "Points" },
        { key: "assignee", label: "Assignee" },
      ],
    },
    {
      key: "projects",
      label: "Projects",
      path: "projects",
      dataKey: "projects",
      columns: [
        { key: "id", label: "ID" },
        { key: "name", label: "Name" },
        { key: "lead", label: "Lead" },
        { key: "status", label: "Status" },
      ],
    },
    {
      key: "developers",
      label: "Developers",
      path: "developers",
      dataKey: "developers",
      columns: [
        { key: "id", label: "ID" },
        { key: "name", label: "Name" },
        { key: "email", label: "Email" },
      ],
    },
  ],
  github: [
    {
      key: "pulls",
      label: "Pull Requests",
      path: "pulls",
      dataKey: "pull_requests",
      columns: [
        { key: "number", label: "#" },
        { key: "title", label: "Title" },
        { key: "author", label: "Author" },
        { key: "status", label: "Status" },
        { key: "repo_id", label: "Repo" },
        { key: "linked_story", label: "Story" },
      ],
    },
    {
      key: "repos",
      label: "Repositories",
      path: "repos",
      dataKey: "repos",
      columns: [
        { key: "id", label: "ID" },
        { key: "name", label: "Name" },
        { key: "language", label: "Language" },
        { key: "open_issues", label: "Open Issues" },
      ],
    },
  ],
  confluence: [
    {
      key: "pages",
      label: "Pages",
      path: "pages",
      dataKey: "pages",
      columns: [
        { key: "id", label: "ID" },
        { key: "title", label: "Title" },
        { key: "space_id", label: "Space" },
        { key: "author", label: "Author" },
        { key: "last_updated", label: "Updated" },
      ],
    },
    {
      key: "spaces",
      label: "Spaces",
      path: "spaces",
      dataKey: "spaces",
      columns: [
        { key: "id", label: "ID" },
        { key: "name", label: "Name" },
        { key: "description", label: "Description" },
      ],
    },
  ],
  servicenow: [
    {
      key: "deployments",
      label: "Deployments",
      path: "deployments",
      dataKey: "deployments",
      columns: [
        { key: "id", label: "ID" },
        { key: "service", label: "Service" },
        { key: "environment", label: "Env" },
        { key: "version", label: "Version" },
        { key: "status", label: "Status" },
        { key: "linked_story", label: "Story" },
      ],
    },
    {
      key: "incidents",
      label: "Incidents",
      path: "incidents",
      dataKey: "incidents",
      columns: [
        { key: "id", label: "ID" },
        { key: "title", label: "Title" },
        { key: "severity", label: "Severity" },
        { key: "status", label: "Status" },
        { key: "affected_service", label: "Service" },
        { key: "linked_deployment", label: "Deployment" },
      ],
    },
  ],
};

type SortDirection = "asc" | "desc";

function formatCell(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function compareValues(a: unknown, b: unknown): number {
  // Push empty values to the end regardless of direction handling upstream.
  const aEmpty = a === null || a === undefined || a === "";
  const bEmpty = b === null || b === undefined || b === "";
  if (aEmpty && bEmpty) return 0;
  if (aEmpty) return 1;
  if (bEmpty) return -1;

  if (typeof a === "number" && typeof b === "number") return a - b;

  const aStr = typeof a === "object" ? JSON.stringify(a) : String(a);
  const bStr = typeof b === "object" ? JSON.stringify(b) : String(b);
  return aStr.localeCompare(bStr, undefined, { numeric: true, sensitivity: "base" });
}

export default function ConnectionDataPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const searchParams = useSearchParams();

  const { integrations, loading: connectionsLoading } = useConnections();
  const integration = useMemo(
    () => integrations.find((i) => String(i.id) === id) ?? null,
    [integrations, id]
  );

  const type = integration?.type ?? "";
  const tabs = useMemo(() => TABS_BY_TYPE[type] ?? [], [type]);

  // Active tab is driven by the URL (?tab=...), falling back to the first tab.
  const tabParam = searchParams.get("tab");
  const activeTab =
    tabs.find((t) => t.key === tabParam)?.key ?? tabs[0]?.key ?? "";
  const currentTab = tabs.find((t) => t.key === activeTab) ?? tabs[0];

  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);
  const [rawJson, setRawJson] = useState<string>("");
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDirection>("asc");
  const [copied, setCopied] = useState(false);

  const setTab = useCallback(
    (key: string) => {
      const next = new URLSearchParams(searchParams.toString());
      next.set("tab", key);
      router.replace(`?${next.toString()}`, { scroll: false });
      setShowRaw(false);
      setQuery("");
      setSortKey(null);
      setSortDir("asc");
    },
    [router, searchParams]
  );

  useEffect(() => {
    if (!integration || !currentTab) return;
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      const result = await api.get<Record<string, unknown>>(
        `/proxy/${type}/${currentTab!.path}`
      );
      if (cancelled) return;
      if (result.error) {
        setError(result.error);
        setRows([]);
        setRawJson("");
      } else {
        const payload = result.data ?? {};
        setRawJson(JSON.stringify(payload, null, 2));
        const data =
          (payload[currentTab!.dataKey] as Record<string, unknown>[]) ?? [];
        setRows(Array.isArray(data) ? data : []);
      }
      setLoading(false);
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [integration, type, currentTab]);

  function toggleSort(key: string) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  async function copyJson() {
    try {
      await navigator.clipboard.writeText(rawJson);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard may be unavailable (e.g. insecure context); fail silently.
    }
  }

  // Filter by the free-text query across all displayed columns, then sort.
  const visibleRows = useMemo(() => {
    const cols = currentTab?.columns ?? [];
    const q = query.trim().toLowerCase();

    let result = rows;
    if (q) {
      result = rows.filter((row) =>
        cols.some((col) => formatCell(row[col.key]).toLowerCase().includes(q))
      );
    }

    if (sortKey) {
      result = [...result].sort((a, b) => {
        const cmp = compareValues(a[sortKey], b[sortKey]);
        return sortDir === "asc" ? cmp : -cmp;
      });
    }

    return result;
  }, [rows, currentTab, query, sortKey, sortDir]);

  // Connection list still loading from the shared context.
  if (connectionsLoading) {
    return (
      <div className="p-8">
        <div className="flex items-center gap-2 text-gray-500">
          <div className="w-4 h-4 border-2 border-gray-300 border-t-blue-500 rounded-full animate-spin" />
          <span>Loading connection...</span>
        </div>
      </div>
    );
  }

  // No matching integration for this id.
  if (!integration) {
    return (
      <div className="p-8">
        <Link
          href="/connections"
          className="text-sm text-blue-600 hover:underline"
        >
          ← Back to Connections
        </Link>
        <div className="mt-6 bg-white rounded-lg shadow p-12 text-center">
          <p className="text-4xl mb-4">🔍</p>
          <p className="text-gray-500 mb-2">Connection not found.</p>
          <p className="text-gray-400 text-sm">
            It may have been removed. Return to the connections list to try again.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8">
      {/* Breadcrumb + header */}
      <nav className="text-sm text-gray-500 mb-3" aria-label="Breadcrumb">
        <Link href="/connections" className="text-blue-600 hover:underline">
          Connections
        </Link>
        <span className="mx-2 text-gray-400">/</span>
        <span className="text-gray-700">{integration.name}</span>
      </nav>

      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">
            {integration.name}
          </h1>
          <p className="text-gray-600 mt-1 capitalize">
            {type} connection
            <span className="ml-2 text-gray-400 normal-case">{integration.url}</span>
          </p>
        </div>
        <Link
          href="/connections"
          className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors text-sm font-medium whitespace-nowrap"
        >
          ← Back
        </Link>
      </div>

      {tabs.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-12 text-center">
          <p className="text-gray-500">
            No browsable data is defined for this connection type.
          </p>
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow">
          {/* Tabs + raw toggle */}
          <div className="flex items-center justify-between px-6 pt-3 border-b border-gray-200 flex-wrap gap-2">
            <div className="flex gap-1 flex-wrap">
              {tabs.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setTab(tab.key)}
                  className={`px-3 py-2 text-sm font-medium rounded-t-lg border-b-2 -mb-px transition-colors ${
                    currentTab?.key === tab.key
                      ? "border-blue-500 text-blue-600"
                      : "border-transparent text-gray-500 hover:text-gray-700"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <button
              onClick={() => setShowRaw((v) => !v)}
              className="px-3 py-1.5 text-xs font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50"
            >
              {showRaw ? "Table view" : "Raw JSON"}
            </button>
          </div>

          {/* Toolbar: search (table mode) or copy (raw mode) */}
          <div className="flex items-center justify-between gap-3 px-6 py-3 border-b border-gray-100">
            {showRaw ? (
              <>
                <span className="text-xs text-gray-400">
                  Raw response from /proxy/{type}/{currentTab?.path}
                </span>
                <button
                  onClick={copyJson}
                  className="px-3 py-1.5 text-xs font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50"
                >
                  {copied ? "Copied!" : "Copy JSON"}
                </button>
              </>
            ) : (
              <>
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search this table..."
                  aria-label="Search table"
                  className="w-full max-w-sm px-3 py-1.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-colors text-sm text-gray-900"
                />
                {!loading && !error && (
                  <span className="text-xs text-gray-400 whitespace-nowrap">
                    {visibleRows.length} of {rows.length} record(s)
                  </span>
                )}
              </>
            )}
          </div>

          {/* Body */}
          <div className="p-6">
            {loading ? (
              <div className="flex items-center gap-2 text-gray-500">
                <div className="w-4 h-4 border-2 border-gray-300 border-t-blue-500 rounded-full animate-spin" />
                <span>Loading data...</span>
              </div>
            ) : error ? (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                {error}
              </div>
            ) : showRaw ? (
              <pre className="text-xs bg-gray-900 text-gray-100 rounded-lg p-4 overflow-auto max-h-[70vh]">
                {rawJson}
              </pre>
            ) : rows.length === 0 ? (
              <p className="text-gray-500 text-sm">No records found.</p>
            ) : visibleRows.length === 0 ? (
              <p className="text-gray-500 text-sm">
                No records match &quot;{query}&quot;.
              </p>
            ) : (
              <div className="overflow-auto">
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="text-left text-gray-500 border-b border-gray-200">
                      {currentTab?.columns.map((col) => {
                        const isSorted = sortKey === col.key;
                        return (
                          <th
                            key={col.key}
                            className="py-2 pr-4 font-medium"
                          >
                            <button
                              onClick={() => toggleSort(col.key)}
                              className="inline-flex items-center gap-1 hover:text-gray-800 transition-colors"
                              aria-label={`Sort by ${col.label}`}
                            >
                              {col.label}
                              <span className="text-gray-300">
                                {isSorted ? (sortDir === "asc" ? "▲" : "▼") : "⇅"}
                              </span>
                            </button>
                          </th>
                        );
                      })}
                    </tr>
                  </thead>
                  <tbody>
                    {visibleRows.map((row, i) => (
                      <tr
                        key={(row.id as string) ?? i}
                        className="border-b border-gray-100 hover:bg-gray-50"
                      >
                        {currentTab?.columns.map((col) => (
                          <td
                            key={col.key}
                            className="py-2 pr-4 text-gray-800 align-top"
                          >
                            {formatCell(row[col.key])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
