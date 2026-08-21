import type { Member } from "../types";

export const MOCK_MEMBERS: Member[] = [
  {
    userId: "u-001",
    workspaceId: "team-001",
    role: "admin",
    status: "active",
    joinedAt: "2026-01-01",
    lastActiveAt: "2026-07-23",
  },
  {
    userId: "u-002",
    workspaceId: "team-001",
    role: "member",
    status: "active",
    joinedAt: "2026-01-15",
    lastActiveAt: "2026-07-22",
  },
  {
    userId: "u-003",
    workspaceId: "team-001",
    role: "member",
    status: "active",
    joinedAt: "2026-02-01",
    lastActiveAt: "2026-07-21",
  },
  {
    userId: "u-004",
    workspaceId: "team-001",
    role: "member",
    status: "active",
    joinedAt: "2026-03-10",
    lastActiveAt: "2026-07-20",
  },
  {
    userId: "u-005",
    workspaceId: "team-001",
    role: "readonly",
    status: "pending",
    joinedAt: "2026-07-20",
    lastActiveAt: "2026-07-20",
  },
];
