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

export interface Document {
  id: number
  workspace_id: number
  parent_id: number | null
  title: string
  content_md: string
  tags: string[]
  author_id: number
  vitality: number
  status: string
  last_interaction_at: string
  created_at: string
}

export interface AttachmentUpload {
  url: string
}

export interface GardenEntry {
  id: number
  title: string
  vitality: number
  status: string
  tags: string[]
  last_interaction_at: string
  author: User
}

export interface MergeRequest {
  id: number
  source_doc_id: number
  target_doc_id: number
  proposer_id: number
  status: string
  created_at: string
  decided_at: string | null
}

export interface TreeNode {
  id: number
  parent_id: number | null
  title: string
  author: User
  vitality: number
  status: string
  merged: boolean
  created_at: string
}
