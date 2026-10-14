/**
 * Shared TypeScript types for MAHALO3 frontend.
 */

export type UserRole = "product_manager" | "developer" | "executive";

export interface User {
  id: number;
  email: string;
  name: string;
  role: UserRole;
  created_at: string;
}

export interface HealthStatus {
  status: string;
  service: string;
  version: string;
}

export interface Integration {
  id: number;
  user_id: number;
  type: "jira" | "confluence" | "github" | "servicenow";
  name: string;
  url: string;
  project_scope: string | null;
  created_at: string;
}

export interface Project {
  id: number;
  user_id: number;
  name: string;
  description: string;
  goal: string;
  project_type: "development" | "maintenance" | "experiment" | "research" | "other";
  status: string;
  jira_project_key: string | null;
  confluence_space_key: string | null;
  github_repo_name: string | null;
  servicenow_service_name: string | null;
  generate_mock_data: boolean;
  is_active: boolean;
  is_selected: boolean;
  created_at: string;
}

export interface ProjectProposal {
  jira_project_key: string;
  confluence_space_key: string;
  github_repo_name: string;
  servicenow_service_name: string;
}
