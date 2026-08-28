import { createBrowserRouter, RouterProvider, Navigate, Outlet } from "react-router";
import "../styles/fonts.css";
import { AuthProvider } from "../auth/AuthProvider";
import { RequireAuth, RequireGuest } from "../auth/RequireAuth";
import { WorkspaceProvider } from "../workspace/WorkspaceProvider";
import { AppShell } from "../components/layout/AppShell";
import { LoginPage } from "../pages/auth/LoginPage";
import { ChangePasswordPage } from "../pages/auth/ChangePasswordPage";
import { HomePage } from "../pages/home/HomePage";
import { IdeaListPage } from "../pages/ideas/IdeaListPage";
import { IdeaDetailPage } from "../pages/ideas/IdeaDetailPage";
import { IdeaEditPage } from "../pages/ideas/IdeaEditPage";
import { AIInputPage } from "../pages/ideas/AIInputPage";
import { AIAnalyzingPage } from "../pages/ideas/AIAnalyzingPage";
import { AIReviewPage } from "../pages/ideas/AIReviewPage";
import { ReviewsPage } from "../pages/reviews/ReviewsPage";
import { MembersPage } from "../pages/workspace/MembersPage";
import { AdminIntegrationsPage } from "../pages/admin/AdminIntegrationsPage";
import { HelpPage } from "../pages/help/HelpPage";

const router = createBrowserRouter([
  {
    element: (
      <AuthProvider>
        <Outlet />
      </AuthProvider>
    ),
    children: [
      {
        element: <RequireGuest />,
        children: [{ path: "/login", element: <LoginPage /> }],
      },
      {
        element: <RequireAuth />,
        children: [
          { path: "/change-password", element: <ChangePasswordPage /> },
          { path: "/admin/integrations", element: <AdminIntegrationsPage /> },
          {
            path: "/w/:workspaceId",
            element: (
              <WorkspaceProvider>
                <AppShell />
              </WorkspaceProvider>
            ),
            children: [
              { path: "home", element: <HomePage /> },
              { path: "ideas", element: <IdeaListPage /> },
              { path: "ideas/new", element: <IdeaEditPage /> },
              { path: "ideas/new/ai", element: <AIInputPage /> },
              {
                path: "ideas/new/ai/analyzing/:sessionId",
                element: <AIAnalyzingPage />,
              },
              {
                path: "ideas/new/ai/review/:sessionId",
                element: <AIReviewPage />,
              },
              {
                // Legacy without sessionId — no mock workflow
                path: "ideas/new/ai/analyzing",
                element: <Navigate to=".." relative="path" replace />,
              },
              {
                path: "ideas/new/ai/review",
                element: <Navigate to=".." relative="path" replace />,
              },
              { path: "ideas/:ideaId", element: <IdeaDetailPage /> },
              { path: "ideas/:ideaId/edit", element: <IdeaEditPage /> },
              { path: "reviews", element: <ReviewsPage /> },
              { path: "settings/members", element: <MembersPage /> },
              { path: "settings", element: <MembersPage /> },
              { path: "help", element: <HelpPage /> },
            ],
          },
        ],
      },
      { path: "/", element: <Navigate to="/login" replace /> },
      { path: "*", element: <Navigate to="/login" replace /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
