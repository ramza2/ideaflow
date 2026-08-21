import { clsx } from "clsx";

interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      className={clsx(
        "rounded-md bg-[#f0f0f5] animate-pulse",
        className
      )}
    />
  );
}

export function IdeaCardSkeleton() {
  return (
    <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-4 space-y-3">
      <div className="flex items-center justify-between">
        <Skeleton className="h-5 w-16" />
        <Skeleton className="h-4 w-8" />
      </div>
      <Skeleton className="h-4 w-4/5" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-3/4" />
      <div className="flex gap-1">
        <Skeleton className="h-4 w-10 rounded-full" />
        <Skeleton className="h-4 w-12 rounded-full" />
        <Skeleton className="h-4 w-8 rounded-full" />
      </div>
      <div className="flex items-center justify-between pt-1">
        <div className="flex items-center gap-2">
          <Skeleton className="w-5 h-5 rounded-full" />
          <Skeleton className="h-3 w-16" />
        </div>
        <div className="flex -space-x-1">
          <Skeleton className="w-5 h-5 rounded-full ring-2 ring-white" />
          <Skeleton className="w-5 h-5 rounded-full ring-2 ring-white" />
        </div>
      </div>
    </div>
  );
}

export function IdeaRowSkeleton() {
  return (
    <div className="flex items-center gap-3 px-4 py-3 border-b border-[rgba(0,0,0,0.04)]">
      <Skeleton className="w-3.5 h-3.5 rounded" />
      <Skeleton className="w-10 h-3" />
      <div className="flex-1 space-y-1.5">
        <Skeleton className="h-3.5 w-48" />
        <Skeleton className="h-3 w-64" />
      </div>
      <Skeleton className="h-5 w-16 rounded-full" />
      <Skeleton className="h-5 w-16 rounded-full" />
      <Skeleton className="h-5 w-14 rounded-full" />
      <Skeleton className="w-5 h-5 rounded-full" />
      <Skeleton className="h-3 w-20" />
      <Skeleton className="w-5 h-5 rounded" />
    </div>
  );
}

export function StatCardSkeleton() {
  return (
    <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-4">
      <Skeleton className="h-7 w-12 mb-1" />
      <Skeleton className="h-3 w-20" />
      <Skeleton className="h-0.5 w-6 mt-2 rounded-full" />
    </div>
  );
}

export function HomePageSkeleton() {
  return (
    <div className="px-4 sm:px-8 py-8 max-w-[1200px] mx-auto space-y-8">
      {/* Header */}
      <div>
        <Skeleton className="h-8 w-52 mb-2" />
        <Skeleton className="h-4 w-72" />
      </div>

      {/* Quick input */}
      <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.07)] p-6">
        <Skeleton className="h-5 w-48 mb-1" />
        <Skeleton className="h-4 w-80 mb-4" />
        <Skeleton className="w-full h-28 rounded-xl" />
        <div className="flex items-center justify-between mt-3">
          <div className="flex gap-4">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-28" />
          </div>
          <div className="flex gap-2">
            <Skeleton className="h-8 w-20 rounded-lg" />
            <Skeleton className="h-8 w-28 rounded-lg" />
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <StatCardSkeleton key={i} />
        ))}
      </div>

      {/* Bottom grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white rounded-2xl border border-[rgba(0,0,0,0.07)] overflow-hidden">
          <div className="px-5 py-4 border-b border-[rgba(0,0,0,0.06)] flex items-center justify-between">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-3 w-16" />
          </div>
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 px-5 py-3.5 border-b border-[rgba(0,0,0,0.04)]">
              <div className="flex-1 space-y-1.5">
                <div className="flex items-center gap-2">
                  <Skeleton className="h-3 w-10" />
                  <Skeleton className="h-4 w-14 rounded-full" />
                </div>
                <Skeleton className="h-3.5 w-48" />
                <Skeleton className="h-3 w-64" />
              </div>
              <Skeleton className="w-5 h-5 rounded-full" />
              <Skeleton className="h-3 w-16" />
            </div>
          ))}
        </div>
        <div className="space-y-4">
          <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.07)]">
            <div className="px-5 py-4 border-b border-[rgba(0,0,0,0.06)]">
              <Skeleton className="h-4 w-20" />
            </div>
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3 px-5 py-3">
                <Skeleton className="w-4 h-4 rounded" />
                <Skeleton className="flex-1 h-3.5" />
                <Skeleton className="w-6 h-5 rounded-full" />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
