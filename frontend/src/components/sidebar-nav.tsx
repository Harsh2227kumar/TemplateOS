import { NavLink } from "react-router-dom";
import { Building2, CloudUpload, LayoutGrid, LayoutDashboard, User, UsersRound } from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { isUserAdmin } from "@/lib/admin-permissions";
import { cn } from "@/lib/utils";

interface NavItem {
  label: string;
  to: string;
  icon: typeof LayoutDashboard;
  comingSoon?: boolean;
}

const navItems: NavItem[] = [
  {
    label: "Dashboard",
    to: "/",
    icon: LayoutDashboard,
  },
  {
    label: "Template Library",
    to: "/templates",
    icon: LayoutGrid,
  },
  {
    label: "Upload Template",
    to: "/upload-template",
    icon: CloudUpload,
  },
  {
    label: "Profile",
    to: "/profile",
    icon: User,
  },
];

/** Shown to super_admin, org_admin and department_admin only. */
const adminItems: NavItem[] = [
  { label: "Users", to: "/admin/users", icon: UsersRound },
  { label: "Organizations", to: "/admin/organizations", icon: Building2 },
];

interface SidebarNavProps {
  onNavigate?: () => void;
}

function NavItemLink({ item, onNavigate }: { item: NavItem; onNavigate?: () => void }) {
  if (item.comingSoon) {
    return (
      <div
        className="flex items-center gap-3 rounded-lg px-3 py-2 text-slate-400 cursor-not-allowed"
        aria-label={`${item.label} (Coming soon)`}
      >
        <item.icon className="h-5 w-5" />
        <span>{item.label}</span>
        <span className="ml-auto text-[10px] uppercase tracking-wider text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">
          Soon
        </span>
      </div>
    );
  }
  return (
    <NavLink
      to={item.to}
      onClick={onNavigate}
      end={item.to === "/"}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-3 rounded-lg px-3 py-2 transition-colors hover:bg-slate-100 hover:text-slate-900",
          isActive && "bg-slate-100 text-slate-900",
        )
      }
    >
      <item.icon className="h-5 w-5" />
      {item.label}
    </NavLink>
  );
}

export function SidebarNav({ onNavigate }: SidebarNavProps) {
  const { user } = useAuth();
  const showAdmin = isUserAdmin(user?.role);

  return (
    <div className="flex flex-col h-full">
      <div className="mb-8 px-2">
        <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-500">
          TemplateOS
        </p>
        <h1 className="mt-2 text-xl font-semibold">Workspace</h1>
      </div>
      <nav className="space-y-1 text-sm font-medium text-slate-600 flex-1">
        {navItems.map((item) => (
          <div key={item.label}>
            <NavItemLink item={item} onNavigate={onNavigate} />
          </div>
        ))}
        {showAdmin && (
          <div className="pt-6" role="group" aria-labelledby="sidebar-admin-heading">
            <p
              id="sidebar-admin-heading"
              className="px-3 pb-2 text-xs font-semibold uppercase tracking-wider text-slate-400"
            >
              Admin
            </p>
            <div className="space-y-1">
              {adminItems.map((item) => (
                <div key={item.label}>
                  <NavItemLink item={item} onNavigate={onNavigate} />
                </div>
              ))}
            </div>
          </div>
        )}
      </nav>
    </div>
  );
}
