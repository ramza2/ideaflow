import { clsx } from "clsx";
import type { User } from "../../types";

interface AvatarProps {
  user: User;
  size?: "xs" | "sm" | "md" | "lg";
  className?: string;
}

const sizeClasses = {
  xs: "w-5 h-5 text-[10px]",
  sm: "w-6 h-6 text-xs",
  md: "w-8 h-8 text-sm",
  lg: "w-10 h-10 text-base",
};

export function Avatar({ user, size = "md", className }: AvatarProps) {
  return (
    <div
      className={clsx(
        "rounded-full flex items-center justify-center font-semibold text-white shrink-0",
        sizeClasses[size],
        className
      )}
      style={{ backgroundColor: user.avatarColor }}
      title={user.name}
    >
      {user.avatarInitials}
    </div>
  );
}

interface AvatarGroupProps {
  users: User[];
  max?: number;
  size?: "xs" | "sm" | "md";
}

export function AvatarGroup({ users, max = 3, size = "sm" }: AvatarGroupProps) {
  const shown = users.slice(0, max);
  const rest = users.length - shown.length;

  return (
    <div className="flex -space-x-1.5">
      {shown.map((u) => (
        <div key={u.id} className="ring-2 ring-white rounded-full">
          <Avatar user={u} size={size} />
        </div>
      ))}
      {rest > 0 && (
        <div
          className={clsx(
            "rounded-full flex items-center justify-center bg-[#e8e8f0] text-[#6b6b80] font-medium ring-2 ring-white",
            size === "xs" && "w-5 h-5 text-[9px]",
            size === "sm" && "w-6 h-6 text-[10px]",
            size === "md" && "w-8 h-8 text-xs"
          )}
        >
          +{rest}
        </div>
      )}
    </div>
  );
}
