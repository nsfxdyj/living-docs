// Tiny fetch wrapper around the JSON API.
// Attaches the stored Bearer token and normalizes errors to `{"detail": ...}`.

const TOKEN_KEY = 'living_docs_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null): void {
  if (token === null) {
    localStorage.removeItem(TOKEN_KEY)
  } else {
    localStorage.setItem(TOKEN_KEY, token)
  }
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    detail: string,
  ) {
    super(detail)
    this.name = 'ApiError'
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
}

async function checkResponse(response: Response): Promise<void> {
  if (response.ok) return
  let detail = response.statusText
  try {
    const data = (await response.json()) as { detail?: unknown }
    if (typeof data.detail === 'string') {
      detail = data.detail
    }
  } catch {
    // Non-JSON error body: keep the HTTP status text.
  }
  throw new ApiError(response.status, detail)
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token !== null) {
    headers.Authorization = `Bearer ${token}`
  }
  const response = await fetch(`/api${path}`, {
    method: options.method ?? 'GET',
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  })
  await checkResponse(response)
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

// Multipart upload (file attachments). The browser sets the Content-Type
// boundary itself, so we must not set a Content-Type header here.
export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token !== null) {
    headers.Authorization = `Bearer ${token}`
  }
  const form = new FormData()
  form.append('file', file)
  const response = await fetch(`/api${path}`, {
    method: 'POST',
    headers,
    body: form,
  })
  await checkResponse(response)
  return (await response.json()) as T
}
