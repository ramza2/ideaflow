import type { Workspace } from "../types";

export const MOCK_WORKSPACES: Workspace[] = [
  { id: "personal", name: "내 작업공간", type: "personal", icon: "👤" },
  { id: "team-001", name: "IdeaFlow Team", type: "team", icon: "💡" },
  { id: "team-002", name: "OpenLink Lab", type: "team", icon: "🔬" },
];

export function getWorkspaceById(id: string): Workspace | undefined {
  return MOCK_WORKSPACES.find((w) => w.id === id);
}
