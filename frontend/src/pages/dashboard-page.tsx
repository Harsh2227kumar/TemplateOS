import { formatDistanceToNow } from "date-fns";
import { FileText, FolderOpen, FileEdit, AlertCircle, ChevronRight } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/auth-context";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { useMyDocuments, useMyTemplates } from "@/hooks/queries";
import { parseServerDate } from "@/lib/dates";

export function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const firstName = user?.full_name?.split(" ")[0] || "User";

  const { data: myTemplatesData, isPending: templatesLoading } = useMyTemplates();
  // A failed templates request shows the empty state, as before.
  const myTemplates = myTemplatesData ?? [];
  const drafts = useMyDocuments();
  const myDrafts = drafts.data ?? [];
  // A retry after an error shows the skeleton again.
  const draftsLoading = drafts.isPending || (drafts.isError && drafts.isFetching);
  // A failed background refetch keeps showing the cached list.
  const draftsError = drafts.isError && !drafts.data
    ? drafts.error.message || "Couldn't load your drafts."
    : null;

  const getCategoryColor = (category: string) => {
    switch (category.toLowerCase()) {
      case "notice": return "bg-blue-100 text-blue-800";
      case "mom": return "bg-purple-100 text-purple-800";
      case "report": return "bg-green-100 text-green-800";
      case "application": return "bg-orange-100 text-orange-800";
      case "letter": return "bg-cyan-100 text-cyan-800";
      case "certificate": return "bg-yellow-100 text-yellow-800";
      case "proposal": return "bg-pink-100 text-pink-800";
      case "invoice": return "bg-slate-100 text-slate-800";
      case "custom": return "bg-gray-100 text-gray-800";
      default: return "bg-gray-100 text-gray-800";
    }
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case "uploaded": return "bg-yellow-400";
      case "active": return "bg-green-400";
      case "field_configured": return "bg-blue-400";
      case "archived": return "bg-gray-400";
      default: return "bg-gray-400";
    }
  };

  const getDraftStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case "draft": return "bg-yellow-100 text-yellow-700";
      case "generated": return "bg-green-100 text-green-700";
      case "submitted": return "bg-blue-100 text-blue-700";
      case "approved": return "bg-purple-100 text-purple-700";
      case "rejected": return "bg-red-100 text-red-700";
      case "final": return "bg-slate-100 text-slate-700";
      default: return "bg-gray-100 text-gray-700";
    }
  };

  const renderTemplatesContent = () => {
    if (templatesLoading) {
      return (
        <div className="space-y-3">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-16 bg-slate-100 rounded-lg animate-pulse" />
          ))}
        </div>
      );
    }
    
    if (myTemplates.length === 0) {
      return (
        <EmptyState
          icon={FolderOpen}
          title="No templates yet"
          description="Uploaded templates, statuses, and quick actions will live in this panel."
          actionLabel="Upload Template"
          onAction={() => navigate("/upload-template")}
        />
      );
    }

    const displayTemplates = myTemplates.slice(0, 5);

    return (
      <div className="flex flex-col h-full">
        <div className="space-y-2 flex-1">
          {displayTemplates.map(t => (
            <div 
              key={t.id}
              onClick={() => navigate(`/templates/${t.id}`)}
              className="flex items-center justify-between p-3 rounded-lg border border-slate-100 hover:bg-slate-50 cursor-pointer transition-colors"
            >
              <div className="flex items-center gap-3 overflow-hidden">
                <div 
                  className={`h-2 w-2 rounded-full shrink-0 ${getStatusColor(t.status)}`}
                  title={`Status: ${t.status}`}
                />
                <div className="min-w-0">
                  <p className="font-medium text-sm text-slate-900 truncate" title={t.name}>
                    {t.name}
                  </p>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(parseServerDate(t.created_at) ?? new Date())}
                  </p>
                </div>
              </div>
              <Badge variant="secondary" className={`ml-2 shrink-0 border-transparent ${getCategoryColor(t.category)}`}>
                {t.category.charAt(0).toUpperCase() + t.category.slice(1)}
              </Badge>
            </div>
          ))}
        </div>
        <div className="mt-4 pt-4 border-t border-slate-100">
          <Link to="/templates" className="text-sm font-medium text-slate-600 hover:text-slate-900">
            View All Templates &rarr;
          </Link>
        </div>
      </div>
    );
  };

  const renderDraftsContent = () => {
    if (draftsLoading) {
      return (
        <div className="space-y-3">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-16 bg-slate-100 rounded-lg animate-pulse" />
          ))}
        </div>
      );
    }

    if (draftsError) {
      return (
        <div className="flex flex-col items-center gap-3 py-6 text-center" role="alert">
          <AlertCircle className="h-8 w-8 text-red-400" />
          <p className="text-sm text-slate-600">{draftsError}</p>
          <Button variant="outline" size="sm" onClick={() => void drafts.refetch()}>
            Retry
          </Button>
        </div>
      );
    }

    if (myDrafts.length === 0) {
      return (
        <EmptyState
          icon={FileEdit}
          title="No drafts yet"
          description="Start filling a form to create your first draft."
          actionLabel="Browse Templates"
          onAction={() => navigate("/templates")}
        />
      );
    }

    const displayDrafts = myDrafts.slice(0, 5);

    const describeUpdated = (value: string) => {
      const date = parseServerDate(value);
      if (!date) return { relative: "unknown", absolute: undefined };
      return { relative: formatDistanceToNow(date, { addSuffix: true }), absolute: date.toLocaleString() };
    };

    return (
      <div className="flex h-full flex-col">
        <ul className="flex-1 space-y-2">
          {displayDrafts.map((d) => {
            const title = d.name || `Draft ${d.id}`;
            const updated = describeUpdated(d.updated_at);
            return (
              <li key={d.id}>
                <Link
                  to={`/documents/${d.id}/edit`}
                  className="group flex items-center gap-3 rounded-lg border border-slate-100 p-3 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
                  aria-label={`Continue editing ${title}`}
                >
                  <div className="h-2 w-2 shrink-0 rounded-full bg-yellow-400" aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-slate-900" title={title}>
                      {title}
                    </p>
                    <p className="mt-0.5 truncate text-xs text-slate-400">
                      {d.template_name || "Unknown template"} ·{" "}
                      <span title={updated.absolute}>edited {updated.relative}</span>
                    </p>
                  </div>
                  <Badge variant="secondary" className={`hidden shrink-0 sm:inline-flex ${getDraftStatusColor(d.status)}`}>
                    {d.status.charAt(0).toUpperCase() + d.status.slice(1)}
                  </Badge>
                  <span className="flex shrink-0 items-center text-sm font-medium text-slate-600 group-hover:text-slate-900">
                    <span className="hidden sm:inline">Continue</span>
                    <ChevronRight className="h-4 w-4" aria-hidden="true" />
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
        {myDrafts.length > displayDrafts.length && (
          <p className="mt-3 text-xs text-slate-500">
            Showing the {displayDrafts.length} most recent of {myDrafts.length} drafts.
          </p>
        )}
      </div>
    );
  };

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      {/* Welcome Hero */}
      <section className="relative overflow-hidden rounded-2xl bg-slate-900 px-6 py-10 sm:px-10 sm:py-12">
        <div className="relative z-10 text-white">
          <p className="text-sm font-medium uppercase tracking-[0.2em] text-slate-400">Document Workspace</p>
          <h1 className="mt-3 text-3xl font-semibold sm:text-4xl">Welcome back, {firstName}</h1>
          <p className="mt-4 max-w-2xl text-base text-slate-300">
            Upload DOCX templates, configure fields, and generate polished documents with AI assistance. Start by uploading a template or browsing the library.
          </p>
          <div className="mt-8 flex flex-wrap gap-4">
            <Button asChild className="bg-white text-slate-900 hover:bg-slate-100">
              <Link to="/upload-template">
                Upload Template
              </Link>
            </Button>
            <Button asChild variant="outline" className="border-slate-600 bg-slate-800/50 text-white hover:bg-slate-700">
              <Link to="/templates">
                Browse Templates
              </Link>
            </Button>
          </div>
        </div>
        {/* Decorative background element */}
        <div className="absolute right-0 top-0 -mr-20 -mt-20 h-64 w-64 rounded-full bg-slate-800 opacity-50 blur-3xl" aria-hidden="true" />
      </section>

      <div className="grid gap-8 lg:grid-cols-3">
        {/* My Drafts - Full width on mobile, 2/3 on desktop */}
        <section className="lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900">My Drafts</h2>
          </div>
          <Card>
            <CardContent className="p-6">
              {renderDraftsContent()}
            </CardContent>
          </Card>
        </section>

        {/* My Templates */}
        <section className="flex flex-col">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900">My Templates</h2>
          </div>
          <Card className="flex-1">
            <CardContent className="p-6">
              {renderTemplatesContent()}
            </CardContent>
          </Card>
        </section>
      </div>
    </div>
  );
}
