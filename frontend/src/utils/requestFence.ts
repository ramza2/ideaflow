/** Workspace-scoped async response fencing (Step 10). */

export function inboxRequestKey(workspaceId: string, tab: string): string {
  return `${workspaceId}:${tab}`;
}

export function shouldApplyRequest(activeKey: string, requestKey: string): boolean {
  return activeKey === requestKey;
}
