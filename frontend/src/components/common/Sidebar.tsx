"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { useProjects } from "@/contexts/ProjectContext";
import { useRequiredConnections } from "@/hooks/useRequiredConnections";
import ProjectMultiSelect from "@/components/common/ProjectMultiSelect";

const ROLE_LABELS: Record<string, string> = {
  product_manager: "Product Manager",
  developer: "Developer",
  executive: "Executive",
};

const navigation = [
  { name: "Dashboard", href: "/dashboard", icon: "📊" },
  { name: "Chat", href: "/chat", icon: "💬" },
  { name: "Connections", href: "/connections", icon: "🔗" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const {
    projects,
    selectedProjects,
    toggleProjectSelection,
    loading: projectsLoading,
    syncing,
    syncProjects,
  } = useProjects();
  const { isConfigured, loading: connectionsLoading } = useRequiredConnections();

  return (
    <aside className="w-64 bg-gray-900 text-white flex flex-col min-h-screen">
      {/* Logo */}
      <div className="p-6 border-b border-gray-700">
        <h1 className="text-xl font-bold tracking-wide">MAHALO3</h1>
        <p className="text-xs text-gray-400 mt-1">AI-Powered SDLC Platform</p>
      </div>

      {/* User section */}
      <div className="p-4 border-b border-gray-700">
        {user ? (
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center text-sm font-medium">
                {user.name.charAt(0).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-white truncate">{user.name}</p>
                <p className="text-xs text-gray-400">
                  {ROLE_LABELS[user.role] || user.role}
                </p>
              </div>
            </div>
            <button
              onClick={logout}
              className="w-full px-3 py-1.5 text-xs text-gray-400 hover:text-white hover:bg-gray-800 rounded transition-colors text-left"
            >
              Sign out
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-gray-600 rounded-full flex items-center justify-center text-sm">
              ?
            </div>
            <div>
              <p className="text-sm text-gray-300">Not logged in</p>
            </div>
          </div>
        )}
      </div>

      {/* Projects selection */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between mb-2">
          <label className="block text-[10px] font-semibold uppercase tracking-wider text-gray-400">
            Projects
          </label>
          <div className="flex items-center gap-2">
            {!projectsLoading && isConfigured && projects.length > 0 && (
              <span className="text-[10px] text-gray-400 font-medium">
                {selectedProjects.length}/{projects.length} in dash
              </span>
            )}
            {!connectionsLoading && !projectsLoading && isConfigured && (
              <button
                type="button"
                onClick={() => {
                  void syncProjects();
                }}
                disabled={syncing}
                title="Import projects from your connected systems"
                className="text-[10px] font-medium text-blue-400 hover:text-blue-300 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {syncing ? "Syncing…" : "Sync"}
              </button>
            )}
          </div>
        </div>

        {connectionsLoading || projectsLoading ? (
          // Skeleton while project/connection data settles so we never flash a
          // misleading empty or "configure connections" state on load.
          <div className="h-9 w-full animate-pulse rounded-lg border border-gray-700 bg-gray-800/60" />
        ) : !isConfigured ? (
          <div className="rounded-lg border border-dashed border-gray-600 bg-gray-800/60 px-3 py-2 text-xs text-gray-400">
            Configure connections to see your projects
          </div>
        ) : projects.length > 0 ? (
          <ProjectMultiSelect
            projects={projects}
            onToggle={toggleProjectSelection}
          />
        ) : (
          <div className="rounded-lg border border-dashed border-gray-600 bg-gray-800/60 px-3 py-2 text-xs text-gray-400">
            No projects yet
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-1">
        {navigation.map((item) => {
          const isActive = pathname?.startsWith(item.href);
          return (
            <Link
              key={item.name}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? "bg-blue-600 text-white"
                  : "text-gray-300 hover:bg-gray-800 hover:text-white"
              }`}
            >
              <span>{item.icon}</span>
              <span>{item.name}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
