import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const cards = [
  {
    title: "Recent Documents",
    body: "Generated files and latest drafts will appear here once document flows are connected.",
  },
  {
    title: "My Templates",
    body: "Uploaded templates, statuses, and quick actions will live in this panel.",
  },
  {
    title: "Project Status",
    body: "Frontend shell, backend API skeleton, and Neon configuration are part of V1.1.",
  },
];

export function DashboardPage() {
  return (
    <div className="space-y-6">
      <section className="rounded-2xl bg-slate-900 p-6 text-white">
        <p className="text-sm uppercase tracking-[0.25em] text-slate-300">Foundation</p>
        <h3 className="mt-2 text-3xl font-semibold">Template-driven document automation</h3>
        <p className="mt-3 max-w-2xl text-sm text-slate-300">
          This starter dashboard gives the team a clean UI shell before authentication,
          template workflows, and AI features are wired in.
        </p>
        <div className="mt-5">
          <Button variant="outline" className="border-slate-600 bg-slate-800 text-white hover:bg-slate-700">
            shadcn/ui base ready
          </Button>
        </div>
      </section>
      <section className="grid gap-4 md:grid-cols-3">
        {cards.map((card) => (
          <Card key={card.title}>
            <CardHeader>
              <CardTitle>{card.title}</CardTitle>
            </CardHeader>
            <CardContent>
              <CardDescription>{card.body}</CardDescription>
            </CardContent>
          </Card>
        ))}
      </section>
    </div>
  );
}
