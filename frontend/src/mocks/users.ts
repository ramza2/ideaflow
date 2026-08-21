import type { User } from "../types";

export const MOCK_USERS: User[] = [
  {
    id: "u-001",
    name: "전창현",
    email: "changhyun@openlink.kr",
    avatarInitials: "전",
    avatarColor: "#4f46e5",
    role: "user",
  },
  {
    id: "u-002",
    name: "김서연",
    email: "seoyeon@openlink.kr",
    avatarInitials: "김",
    avatarColor: "#7c3aed",
    role: "user",
  },
  {
    id: "u-003",
    name: "박민준",
    email: "minjun@openlink.kr",
    avatarInitials: "박",
    avatarColor: "#0891b2",
    role: "user",
  },
  {
    id: "u-004",
    name: "이지은",
    email: "jieun@openlink.kr",
    avatarInitials: "이",
    avatarColor: "#16a34a",
    role: "user",
  },
  {
    id: "u-005",
    name: "최동훈",
    email: "donghun@openlink.kr",
    avatarInitials: "최",
    avatarColor: "#d97706",
    role: "user",
  },
  {
    id: "u-admin",
    name: "관리자",
    email: "admin@openlink.kr",
    avatarInitials: "관",
    avatarColor: "#dc2626",
    role: "admin",
  },
];

export const CURRENT_USER = MOCK_USERS[0];

export function getUserById(id: string): User | undefined {
  return MOCK_USERS.find((u) => u.id === id);
}
