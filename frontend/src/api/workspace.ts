/** Authenticated client for the tenant-scoped workspace API. */
export async function workspaceRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const token = sessionStorage.getItem('workspace_token');
  const response = await fetch(`/api/v1/workspace${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  });
  const body = await response.json().catch(() => ({})) as T & { detail?: string };
  if (!response.ok) throw new Error(body.detail ?? `Request failed (${response.status})`);
  return body;
}
