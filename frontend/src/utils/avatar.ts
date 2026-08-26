import type { User } from "../types";
import type { IdeaUserRef } from "../types/api";

const AVATAR_COLORS = [
  "#4f46e5",
  "#7c3aed",
  "#2563eb",
  "#0891b2",
  "#059669",
  "#d97706",
  "#dc2626",
  "#db2777",
];

function hashString(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

function initialsFromName(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "?";
  const parts = trimmed.split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  if (trimmed.length >= 2) return trimmed.slice(0, 2).toUpperCase();
  return trimmed[0].toUpperCase();
}

export function toDisplayUser(
  ref: IdeaUserRef | { id: string; name: string; email?: string },
  role: User["role"] = "user",
): User {
  const email = "email" in ref ? (ref.email ?? "") : "";
  return {
    id: ref.id,
    name: ref.name,
    email,
    avatarInitials: initialsFromName(ref.name),
    avatarColor: AVATAR_COLORS[hashString(ref.id) % AVATAR_COLORS.length],
    role,
  };
}
