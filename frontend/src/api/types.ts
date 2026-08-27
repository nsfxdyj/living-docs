// Shared API response types (mirrors backend/app/schemas.py).

export interface User {
  id: number
  email: string
  display_name: string
}

export interface AuthResponse {
  token: string
  user: User
}

export interface Workspace {
  id: number
  name: string
  slug: string
  owner_id: number
  role: string | null
}

export interface Member {
  user_id: number
  email: string
  display_name: string
  role: string
}

export interface WorkspaceDetail extends Workspace {
  members: Member[]
}

export interface Invite {
  token: string
  url: string
  expires_at: string
}
