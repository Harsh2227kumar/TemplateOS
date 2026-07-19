import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";
import { cn } from "@/lib/utils";

const navItemClassName = ({ isActive }: { isActive: boolean }) =>
  cn(
    "block rounded-lg px-3 py-2 transition-colors hover:bg-slate-100",
    isActive && "bg-slate-100 font-medium text-slate-900",
  );

export function DashboardLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <div className="mx-auto grid min-h-screen max-w-7xl grid-cols-1 lg:grid-cols-[260px_1fr]">
        <aside className="border-r border-slate-200 bg-white p-6">
          <div className="mb-8">
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-500">
              TemplateOS
            </p>
            <h1 className="mt-2 text-2xl font-semibold">Document Workspace</h1>
          </div>
          <nav className="space-y-2 text-sm text-slate-600">
            <NavLink className={navItemClassName} to="/" end>
              Dashboard
            </NavLink>
            <NavLink className={navItemClassName} to="/profile">
              Profile
            </NavLink>
          </nav>
        </aside>
        <main className="flex min-h-screen flex-col">
          <header className="border-b border-slate-200 bg-white px-6 py-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-slate-500">V1.1 Project Foundation</p>
                <h2 className="text-xl font-semibold">Dashboard Shell</h2>
              </div>
              <div className="flex items-center gap-3">
                <div className="hidden text-right sm:block">
                  <p className="text-sm font-medium">{user?.full_name}</p>
                  <p className="text-xs capitalize text-slate-500">{user?.role.split("_").join(" ")}</p>
                </div>
                <Button variant="outline" onClick={handleLogout}>
                  Log out
                </Button>
              </div>
            </div>
          </header>
          <div className="flex-1 p-6">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
