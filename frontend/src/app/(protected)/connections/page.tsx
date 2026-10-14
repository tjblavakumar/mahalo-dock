"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/services/api";
import { useProjects } from "@/contexts/ProjectContext";
import { useRequiredConnections } from "@/hooks/useRequiredConnections";
import type { Integration, Project, ProjectProposal } from "@/types";

interface TestResult {
  success: boolean;
  message: string;
  service_info?: Record<string, string>;
}

const INTEGRATION_TYPES = [
  { value: "jira", label: "Jira", icon: "📋", defaultPort: 5001 },
  { value: "confluence", label: "Confluence", icon: "📄", defaultPort: 5002 },
  { value: "github", label: "GitHub", icon: "🐙", defaultPort: 5003 },
  { value: "servicenow", label: "ServiceNow", icon: "🛠️", defaultPort: 5004 },
];

const PROJECT_TYPES = [
  { value: "development", label: "Development" },
  { value: "maintenance", label: "Maintenance" },
  { value: "experiment", label: "Experiment" },
  { value: "research", label: "Research" },
  { value: "other", label: "Other" },
];

export default function ConnectionsPage() {
  const { projects, selectedProjects, toggleProjectSelection, refreshProjects } = useProjects();
  const [showForm, setShowForm] = useState(false);
  const [showProjectForm, setShowProjectForm] = useState(false);
  const [testResults, setTestResults] = useState<Record<number, TestResult>>({});
  const [testingId, setTestingId] = useState<number | null>(null);
  const [projectProposal, setProjectProposal] = useState<ProjectProposal | null>(null);
  const [projectFormError, setProjectFormError] = useState<string | null>(null);
  const [projectSubmitting, setProjectSubmitting] = useState(false);

  const [formType, setFormType] = useState("jira");
  const [formName, setFormName] = useState("");
  const [formUrl, setFormUrl] = useState("");
  const [formToken, setFormToken] = useState("");
  const [formScope, setFormScope] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [projectName, setProjectName] = useState("");
  const [projectDescription, setProjectDescription] = useState("");
  const [projectGoal, setProjectGoal] = useState("");
  const [projectType, setProjectType] = useState("development");
  const [generateMockData, setGenerateMockData] = useState(true);

  const {
    integrations,
    isConfigured: allRequiredConnectionsReady,
    loading: connectionsLoading,
    refresh: refreshIntegrations,
  } = useRequiredConnections();

  // The connections list is sourced from the shared ConnectionsContext, which
  // waits for auth before fetching. `loading` mirrors that shared state.
  const loading = connectionsLoading;

  useEffect(() => {
    void refreshProjects();
  }, [refreshProjects]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setSubmitting(true);

    const result = await api.post<Integration>("/integrations", {
      type: formType,
      name: formName,
      url: formUrl,
      token: formToken,
      project_scope: formScope || null,
    });

    if (result.error) {
      setFormError(result.error);
    } else {
      setShowForm(false);
      resetForm();
      // Refresh the shared connections context so sidebar/dashboard update immediately
      await refreshIntegrations();
    }
    setSubmitting(false);
  }

  async function handleTest(id: number) {
    setTestingId(id);
    const result = await api.post<TestResult>(`/integrations/${id}/test`, {});
    if (result.data) {
      setTestResults((prev) => ({ ...prev, [id]: result.data! }));
    }
    setTestingId(null);
  }

  async function handleDelete(id: number) {
    await api.delete(`/integrations/${id}`);
    setTestResults((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    // Refresh the shared connections context so this page, the sidebar, and the
    // dashboard all update immediately from a single source of truth.
    await refreshIntegrations();
  }

  async function handleDeleteProject(projectId: number) {
    if (!confirm("Are you sure you want to delete this project?")) return;
    await api.delete(`/projects/${projectId}`);
    await refreshProjects();
  }

  async function handleProjectProposal() {
    setProjectFormError(null);
    const result = await api.post<ProjectProposal>("/projects/proposal", {
      name: projectName,
      description: projectDescription,
      goal: projectGoal,
      project_type: projectType,
    });

    if (result.error) {
      setProjectFormError(result.error);
      return;
    }

    setProjectProposal(result.data);
  }

  async function handleCreateProject() {
    if (!projectProposal) return;
    setProjectSubmitting(true);
    setProjectFormError(null);

    const result = await api.post<Project>("/projects", {
      name: projectName,
      description: projectDescription,
      goal: projectGoal,
      project_type: projectType,
      jira_project_key: projectProposal.jira_project_key,
      confluence_space_key: projectProposal.confluence_space_key,
      github_repo_name: projectProposal.github_repo_name,
      servicenow_service_name: projectProposal.servicenow_service_name,
      generate_mock_data: generateMockData,
    });

    if (result.error) {
      setProjectFormError(result.error);
    } else {
      setShowProjectForm(false);
      setProjectProposal(null);
      setProjectName("");
      setProjectDescription("");
      setProjectGoal("");
      setProjectType("development");
      setGenerateMockData(true);
      await refreshProjects();
    }
    setProjectSubmitting(false);
  }

  function resetForm() {
    setFormType("jira");
    setFormName("");
    setFormUrl("");
    setFormToken("");
    setFormScope("");
    setFormError(null);
  }

  function prefillDefaults(type: string) {
    setFormType(type);
    const config = INTEGRATION_TYPES.find((t) => t.value === type);
    if (config) {
      setFormName(`My ${config.label}`);
      setFormUrl(`http://localhost:${config.defaultPort}`);
      setFormToken(`mock-${type}-token-12345`);
    }
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Connections</h1>
          <p className="text-gray-600 mt-1">
            Manage your integrations with Jira, Confluence, GitHub, and ServiceNow.
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => setShowProjectForm(true)}
            disabled={!allRequiredConnectionsReady}
            title={
              !allRequiredConnectionsReady
                ? "Configure Jira, Confluence, and GitHub connections before creating a project."
                : ""
            }
            className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            + Create New Project
          </button>
          <button
            onClick={() => setShowForm(true)}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
          >
            + Add Connection
          </button>
        </div>
      </div>

      {showForm && (
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">
            Add Connection
          </h2>

          {formError && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm mb-4">
              {formError}
            </div>
          )}

          <form onSubmit={handleCreate} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Service type</label>
                <select
                  value={formType}
                  onChange={(e) => {
                    const nextType = e.target.value;
                    setFormType(nextType);
                    prefillDefaults(nextType);
                  }}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-colors text-gray-900 bg-white"
                >
                  {INTEGRATION_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>{type.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Connection name</label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-colors text-gray-900"
                  placeholder="My Jira"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Base URL</label>
                <input
                  type="url"
                  value={formUrl}
                  onChange={(e) => setFormUrl(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-colors text-gray-900"
                  placeholder="http://localhost:5001"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Token</label>
                <input
                  type="text"
                  value={formToken}
                  onChange={(e) => setFormToken(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-colors text-gray-900"
                  placeholder="mock-jira-token-12345"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Project scope (optional)</label>
              <input
                type="text"
                value={formScope}
                onChange={(e) => setFormScope(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-colors text-gray-900"
                placeholder="project or team scope"
              />
            </div>

            <div className="flex gap-3 pt-2">
              <button
                type="submit"
                disabled={submitting}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium disabled:opacity-50"
              >
                {submitting ? "Adding..." : "Save Connection"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowForm(false);
                  resetForm();
                }}
                className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors text-sm"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {showProjectForm && (
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">
            Create New Project
          </h2>

          {projectFormError && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm mb-4">
              {projectFormError}
            </div>
          )}

          {!projectProposal ? (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Project name</label>
                <input
                  type="text"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg ..."
                  placeholder="Customer Portal"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Project description</label>
                <textarea
                  value={projectDescription}
                  onChange={(e) => setProjectDescription(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg ..."
                  rows={3}
                  placeholder="Brief project description"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Goal of the project</label>
                <textarea
                  value={projectGoal}
                  onChange={(e) => setProjectGoal(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg ..."
                  rows={3}
                  placeholder="What problem does this project solve?"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Project type</label>
                <select
                  value={projectType}
                  onChange={(e) => setProjectType(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg ..."
                >
                  {PROJECT_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>{type.label}</option>
                  ))}
                </select>
              </div>

              <div className="flex items-center gap-2">
                <input
                  id="generateMockData"
                  type="checkbox"
                  checked={generateMockData}
                  onChange={(e) => setGenerateMockData(e.target.checked)}
                />
                <label htmlFor="generateMockData" className="text-sm text-gray-700">
                  Generate mock data for this project
                </label>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={handleProjectProposal}
                  className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors text-sm font-medium"
                >
                  Propose Project IDs
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowProjectForm(false);
                    setProjectProposal(null);
                    setProjectName("");
                    setProjectDescription("");
                    setProjectGoal("");
                    setProjectType("development");
                    setGenerateMockData(true);
                  }}
                  className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors text-sm"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="bg-purple-50 border border-purple-200 rounded-lg p-4 text-sm text-purple-900">
                Proposed values are ready. Review and approve to create the project.
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="border rounded-lg p-3">
                  <div className="text-xs uppercase text-gray-500 mb-1">Jira key</div>
                  <div className="font-semibold">{projectProposal.jira_project_key}</div>
                </div>
                <div className="border rounded-lg p-3">
                  <div className="text-xs uppercase text-gray-500 mb-1">Confluence key</div>
                  <div className="font-semibold">{projectProposal.confluence_space_key}</div>
                </div>
                <div className="border rounded-lg p-3">
                  <div className="text-xs uppercase text-gray-500 mb-1">GitHub repo</div>
                  <div className="font-semibold">{projectProposal.github_repo_name}</div>
                </div>
                <div className="border rounded-lg p-3">
                  <div className="text-xs uppercase text-gray-500 mb-1">ServiceNow service</div>
                  <div className="font-semibold">{projectProposal.servicenow_service_name}</div>
                </div>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={handleCreateProject}
                  disabled={projectSubmitting}
                  className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm font-medium disabled:opacity-50"
                >
                  {projectSubmitting ? "Creating..." : "Approve & Create Project"}
                </button>
                <button
                  type="button"
                  onClick={() => setProjectProposal(null)}
                  className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors text-sm"
                >
                  Edit proposal
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {!connectionsLoading && !allRequiredConnectionsReady && (
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <div className="text-center py-8">
            <p className="text-4xl mb-4">📁</p>
            <p className="text-gray-500 mb-2">Connect required services to view your projects.</p>
            <p className="text-gray-400 text-sm">
              Configure{" "}
              <Link href="/connections" className="text-blue-600 hover:underline font-medium">
                Jira, Confluence, and GitHub
              </Link>{" "}
              to access your project data.
            </p>
          </div>
        </div>
      )}

      {allRequiredConnectionsReady && projects.length > 0 && (
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
            <div>
              <h2 className="text-lg font-semibold text-gray-800">Projects</h2>
              <p className="text-xs text-gray-500">
                Check projects to include them in the Dashboard. All checked projects will be aggregated across all dashboard widgets.
              </p>
            </div>
            <div className="text-xs font-medium text-blue-700 bg-blue-50 px-3 py-1 rounded-full border border-blue-200 self-start sm:self-auto">
              {selectedProjects.length} of {projects.length} included in dashboard
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {projects.map((project) => (
              <div
                key={project.id}
                onClick={() => toggleProjectSelection(project.id)}
                className={`border rounded-lg p-4 cursor-pointer transition-all ${
                  project.is_selected
                    ? "border-blue-400 bg-blue-50/40 ring-1 ring-blue-300 shadow-sm"
                    : "border-gray-200 bg-white hover:border-gray-300 opacity-75"
                }`}
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="min-w-0 flex-1">
                    <h3 className="font-semibold text-gray-900 truncate">{project.name}</h3>
                    <p className="text-xs text-gray-500 line-clamp-1">{project.description || "No description."}</p>
                  </div>
                  <input
                    type="checkbox"
                    checked={project.is_selected}
                    onChange={(e) => {
                      e.stopPropagation();
                      toggleProjectSelection(project.id);
                    }}
                    className="h-4 w-4 mt-0.5 rounded accent-blue-600 cursor-pointer"
                  />
                </div>

                <div className="pt-2 border-t border-gray-100 space-y-1 text-xs text-gray-600">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Jira:</span>
                    <span className="font-mono text-gray-700">{project.jira_project_key || "—"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Confluence:</span>
                    <span className="font-mono text-gray-700">{project.confluence_space_key || "—"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">GitHub:</span>
                    <span className="font-mono text-gray-700">{project.github_repo_name || "—"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">ServiceNow:</span>
                    <span className="font-mono text-gray-700">{project.servicenow_service_name || "—"}</span>
                  </div>
                </div>

                <div className="mt-3 pt-2 border-t border-gray-100 flex items-center justify-between text-xs">
                  <span className={project.is_selected ? "text-blue-700 font-medium" : "text-gray-400"}>
                    {project.is_selected ? "✓ Included in Dashboard" : "Excluded from Dashboard"}
                  </span>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteProject(project.id);
                    }}
                    className="text-gray-400 hover:text-red-600 transition-colors px-1.5 py-0.5 rounded hover:bg-red-50 text-[11px]"
                    title="Delete project"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-gray-500">
          <div className="w-4 h-4 border-2 border-gray-300 border-t-blue-500 rounded-full animate-spin" />
          <span>Loading connections...</span>
        </div>
      ) : integrations.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-12 text-center">
          <p className="text-4xl mb-4">🔗</p>
          <p className="text-gray-500 mb-2">No connections configured yet.</p>
          <p className="text-gray-400 text-sm">
            Click &quot;Add Connection&quot; to connect Jira, Confluence, or GitHub.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {integrations.map((integration) => {
            const typeConfig = INTEGRATION_TYPES.find(
              (t) => t.value === integration.type
            );
            const testResult = testResults[integration.id];

            return (
              <div
                key={integration.id}
                className="bg-white rounded-lg shadow p-5 flex items-center justify-between"
              >
                <div className="flex items-center gap-4">
                  <span className="text-3xl">
                    {typeConfig?.icon || "🔗"}
                  </span>
                  <div>
                    <h3 className="font-medium text-gray-900">
                      {integration.name}
                    </h3>
                    <p className="text-sm text-gray-500">
                      {integration.url}
                      {integration.project_scope && (
                        <span className="ml-2 px-2 py-0.5 bg-gray-100 rounded text-xs">
                          {integration.project_scope}
                        </span>
                      )}
                    </p>
                    {testResult && (
                      <p
                        className={`text-xs mt-1 ${
                          testResult.success
                            ? "text-green-600"
                            : "text-red-600"
                        }`}
                      >
                        {testResult.success ? "✓" : "✗"}{" "}
                        {testResult.message}
                      </p>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleTest(integration.id)}
                    disabled={testingId === integration.id}
                    className="px-3 py-1.5 bg-green-50 text-green-700 border border-green-200 rounded-lg hover:bg-green-100 transition-colors text-xs font-medium disabled:opacity-50"
                  >
                    {testingId === integration.id ? "Testing..." : "Test"}
                  </button>
                  <Link
                    href={`/connections/${integration.id}/data`}
                    className="px-3 py-1.5 bg-blue-50 text-blue-700 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors text-xs font-medium"
                  >
                    View data
                  </Link>
                  <button
                    onClick={() => handleDelete(integration.id)}
                    className="px-3 py-1.5 bg-red-50 text-red-700 border border-red-200 rounded-lg hover:bg-red-100 transition-colors text-xs font-medium"
                  >
                    Remove
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

    </div>
  );
}
