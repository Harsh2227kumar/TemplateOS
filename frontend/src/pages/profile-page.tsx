import { useAuth } from "@/context/auth-context";

export function ProfilePage() {
  const { user } = useAuth();

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <p className="text-sm uppercase tracking-[0.2em] text-slate-500">Profile</p>
      <h1 className="mt-2 text-2xl font-semibold">My Profile</h1>
      <p className="mt-3 text-sm text-slate-600">
        Your account details and current TemplateOS role.
      </p>
      <dl className="mt-8 grid gap-5 sm:grid-cols-2">
        <div>
          <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Full name</dt>
          <dd className="mt-1 text-base text-slate-900">{user?.full_name}</dd>
        </div>
        <div>
          <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Email</dt>
          <dd className="mt-1 text-base text-slate-900">{user?.email}</dd>
        </div>
        <div>
          <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Role</dt>
          <dd className="mt-1 inline-flex rounded-full bg-slate-100 px-3 py-1 text-sm capitalize text-slate-700">
            {user?.role.split("_").join(" ")}
          </dd>
        </div>
      </dl>
    </section>
  );
}
