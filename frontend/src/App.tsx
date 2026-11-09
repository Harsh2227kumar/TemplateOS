import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute, PublicOnlyRoute } from "./components/protected-route";
import { DashboardLayout } from "./layouts/dashboard-layout";
import { DashboardPage } from "./pages/dashboard-page";
import { LoginPage } from "./pages/login-page";
import { EklinkCallbackPage } from "./pages/eklink-callback-page";
import { ProfilePage } from "./pages/profile-page";
import { UploadTemplatePage } from "./pages/upload-template-page";
import { SignupPage } from "./pages/signup-page";
import { TemplateLibraryPage } from "./pages/template-library-page";
import { TemplateDetailPage } from "./pages/template-detail-page";
import { PlaceholderReviewPage } from "./pages/placeholder-review-page";
import { TemplateCleaningPage } from "./pages/template-cleaning-page";
import { FieldSetupPage } from "./pages/field-setup-page";
import { CreateDocumentPage } from "./pages/create-document-page";
import { EditDocumentPage } from "./pages/edit-document-page";
import { DocumentPreviewPage } from "./pages/document-preview-page";
import { AdminRoute } from "./features/admin/AdminRoute";
import { DraftLoadingSkeleton } from "./features/documents/DraftLoadStates";
import { AdminUsersPage } from "./pages/admin-users-page";
import { AdminOrganizationsPage } from "./pages/admin-organizations-page";
import { AdminApproversPage } from "./pages/admin-approvers-page";
import { AdminSyncPage } from "./pages/admin-sync-page";

// V1.7 P2: the version view loads on demand.
const DocumentVersionPage = lazy(() =>
  import("./pages/document-version-page").then((module) => ({ default: module.DocumentVersionPage })),
);
// V1.7 P2.1: the Word file editor pages (ONLYOFFICE) load on demand.
const TemplateFileEditorPage = lazy(() =>
  import("./pages/template-file-editor-page").then((module) => ({ default: module.TemplateFileEditorPage })),
);
const DocumentFileEditorPage = lazy(() =>
  import("./pages/document-file-editor-page").then((module) => ({ default: module.DocumentFileEditorPage })),
);
// V1.7 P3: download history and the admin audit log load on demand.
const DownloadsPage = lazy(() =>
  import("./pages/downloads-page").then((module) => ({ default: module.DownloadsPage })),
);
const AdminAuditLogPage = lazy(() =>
  import("./pages/admin-audit-log-page").then((module) => ({ default: module.AdminAuditLogPage })),
);
const TemplateFieldChangesPage = lazy(() =>
  import("./pages/template-field-changes-page").then((module) => ({ default: module.TemplateFieldChangesPage })),
);

export function App() {
  return (
    <Routes>
      {/* Not public-only: an EkLink launch may replace another signed-in account. */}
      <Route path="/auth/callback" element={<EklinkCallbackPage />} />
      <Route element={<PublicOnlyRoute />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
      </Route>
      <Route element={<ProtectedRoute />}>
        <Route element={<DashboardLayout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route
            path="/downloads"
            element={
              <Suspense fallback={<DraftLoadingSkeleton />}>
                <DownloadsPage />
              </Suspense>
            }
          />
          <Route path="/upload-template" element={<UploadTemplatePage />} />
          <Route path="/templates" element={<TemplateLibraryPage />} />
          <Route path="/templates/:id" element={<TemplateDetailPage />} />
          <Route path="/templates/:id/placeholders" element={<PlaceholderReviewPage />} />
          <Route path="/templates/:id/clean" element={<TemplateCleaningPage />} />
          <Route path="/templates/:id/fields" element={<FieldSetupPage />} />
          <Route
            path="/templates/:id/edit-file"
            element={
              <Suspense fallback={<DraftLoadingSkeleton />}>
                <TemplateFileEditorPage />
              </Suspense>
            }
          />
          <Route
            path="/templates/:id/field-changes"
            element={
              <Suspense fallback={<DraftLoadingSkeleton />}>
                <TemplateFieldChangesPage />
              </Suspense>
            }
          />
          <Route path="/documents/create/:id" element={<CreateDocumentPage />} />
          <Route path="/documents/:id/edit" element={<EditDocumentPage />} />
          <Route path="/documents/:id/preview" element={<DocumentPreviewPage />} />
          <Route
            path="/documents/:id/edit-file"
            element={
              <Suspense fallback={<DraftLoadingSkeleton />}>
                <DocumentFileEditorPage />
              </Suspense>
            }
          />
          <Route
            path="/documents/:id/versions/:version"
            element={
              <Suspense fallback={<DraftLoadingSkeleton />}>
                <DocumentVersionPage />
              </Suspense>
            }
          />
          {/* super_admin / org_admin / institute_admin / department_admin only */}
          <Route element={<AdminRoute />}>
            <Route path="/admin" element={<Navigate to="/admin/users" replace />} />
            <Route path="/admin/users" element={<AdminUsersPage />} />
            <Route path="/admin/organizations" element={<AdminOrganizationsPage />} />
            <Route path="/admin/approvers" element={<AdminApproversPage />} />
            <Route path="/admin/sync" element={<AdminSyncPage />} />
            <Route
              path="/admin/audit-log"
              element={
                <Suspense fallback={<DraftLoadingSkeleton />}>
                  <AdminAuditLogPage />
                </Suspense>
              }
            />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
