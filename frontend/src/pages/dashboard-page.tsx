import { FileText, FolderOpen } from "lucide-react";

import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/auth-context";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";

export function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const firstName = user?.full_name?.split(" ")[0] || "User";

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      {/* Welcome Hero */}
      <section className="relative overflow-hidden rounded-2xl bg-slate-900 px-6 py-10 sm:px-10 sm:py-12">
        <div className="relative z-10 text-white">
          <p className="text-sm font-medium uppercase tracking-[0.2em] text-slate-400">Foundation</p>
          <h1 className="mt-3 text-3xl font-semibold sm:text-4xl">Welcome back, {firstName}</h1>
          <p className="mt-4 max-w-2xl text-base text-slate-300">
            This starter dashboard provides a clean UI shell. Template workflows, document generation, and AI features will be connected in upcoming phases.
          </p>
          <div className="mt-8 flex flex-wrap gap-4">
            <Button asChild className="bg-white text-slate-900 hover:bg-slate-100">
              <a href={(import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1").replace("/api/v1", "/docs")} target="_blank" rel="noopener noreferrer">
                View Documentation
              </a>
            </Button>
            <Button variant="outline" className="border-slate-600 bg-slate-800/50 text-white hover:bg-slate-700">
              shadcn/ui ready
            </Button>
          </div>
        </div>
        {/* Decorative background element */}
        <div className="absolute right-0 top-0 -mr-20 -mt-20 h-64 w-64 rounded-full bg-slate-800 opacity-50 blur-3xl" aria-hidden="true" />
      </section>

      <div className="grid gap-8 lg:grid-cols-2">
        {/* Recent Documents */}
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900">Recent Documents</h2>
          </div>
          <EmptyState
            icon={FileText}
            title="No recent documents yet"
            description="Generated files and latest drafts will appear here once document flows are connected."
            actionLabel="Create Document"
          />
        </section>

        {/* My Templates */}
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900">My Templates</h2>
          </div>
          <EmptyState
            icon={FolderOpen}
            title="No templates yet"
            description="Uploaded templates, statuses, and quick actions will live in this panel."
            actionLabel="Upload Template"
            onAction={() => navigate("/upload-template")}
          />
        </section>
      </div>
    </div>
  );
}
