export type Repository = {
  id: number; name: string; source: string; status: string;
  profile: Record<string, any>;
};

export type Run = {
  id: number; repository_id: number; kind: string; status: string;
  request: string; result: Record<string, any>;
};

export type TestSummary = { outcome:string; headline:string; passed:number; failed:number; errors:number; skipped:number; warnings:number; completed_tests:number; cause:string; recommended_action:string };
export type TestRun = { id:number; repository_id:number; status:string; exit_code:number; duration_ms:number; output:string; stdout?:string; stderr?:string; summary?:TestSummary };
export type ReportSummary = { id:number; repository_id:number; repository_name:string; kind:string; status:string; request:string; created_at:string; verification?:any; finding_count:number };

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers }, ...init,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  return response.json();
}

export const api = {
  repositories: () => request<Repository[]>("/repositories"),
  addLocal: (local_path: string) => request<Repository>("/repositories", { method: "POST", body: JSON.stringify({ local_path }) }),
  addGithub: (github_url: string) => request<Repository>("/repositories", { method: "POST", body: JSON.stringify({ github_url }) }),
  scan: (id: number) => request<Repository>(`/repositories/${id}/scan`, { method: "POST" }),
  structure: (id: number) => request<{ files: any[] }>(`/repositories/${id}/structure`),
  analyze: (repository_id: number) => request<Run>("/analysis", { method: "POST", body: JSON.stringify({ repository_id }) }),
  debug: (repository_id: number, problem: string) => request<Run>("/debug", { method: "POST", body: JSON.stringify({ repository_id, problem }) }),
  testRuns: (repository_id?: number) => request<TestRun[]>(`/tests${repository_id ? `?repository_id=${repository_id}` : ""}`),
  runTests: (repository_id: number, runner: "pytest" | "npm_test") => request<TestRun>("/tests/run", { method: "POST", body: JSON.stringify({ repository_id, runner }) }),
  reports: (repository_id?: number) => request<ReportSummary[]>(`/reports${repository_id ? `?repository_id=${repository_id}` : ""}`),
  report: (id: number) => request<any>(`/reports/${id}`),
};
