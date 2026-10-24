import { TemplateListItem } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Lock, Globe, Building, Users, UsersRound, ShieldCheck, Copy } from "lucide-react";
import { describeRoles } from "@/components/templates/AudienceFields";
import { copyBadgeText } from "@/features/word-editor/word-editor-model";

interface TemplateCardProps {
  template: TemplateListItem;
  onClick: (id: number) => void;
}

export function TemplateCard({ template, onClick }: TemplateCardProps) {
  const getCategoryColor = (category: string) => {
    switch (category.toLowerCase()) {
      case "notice": return "bg-blue-100 text-blue-800 hover:bg-blue-100";
      case "mom": return "bg-purple-100 text-purple-800 hover:bg-purple-100";
      case "report": return "bg-green-100 text-green-800 hover:bg-green-100";
      case "application": return "bg-orange-100 text-orange-800 hover:bg-orange-100";
      case "letter": return "bg-cyan-100 text-cyan-800 hover:bg-cyan-100";
      case "certificate": return "bg-yellow-100 text-yellow-800 hover:bg-yellow-100";
      case "proposal": return "bg-pink-100 text-pink-800 hover:bg-pink-100";
      case "invoice": return "bg-slate-100 text-slate-800 hover:bg-slate-100";
      case "custom": return "bg-gray-100 text-gray-800 hover:bg-gray-100";
      default: return "bg-gray-100 text-gray-800 hover:bg-gray-100";
    }
  };

  const VisibilityIcon = () => {
    switch (template.visibility.toLowerCase()) {
      case "private": return <Lock className="mr-1 h-3 w-3" />;
      case "public": return <Globe className="mr-1 h-3 w-3" />;
      case "organization": return <Building className="mr-1 h-3 w-3" />;
      case "department": return <Users className="mr-1 h-3 w-3" />;
      case "group": return <UsersRound className="mr-1 h-3 w-3" />;
      default: return <Lock className="mr-1 h-3 w-3" />;
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

  const copyBadge = copyBadgeText(template);

  const formattedDate = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(template.created_at));

  return (
    <Card 
      className="cursor-pointer overflow-hidden transition-all hover:scale-[1.02] hover:shadow-lg min-h-[160px] flex flex-col"
      onClick={() => onClick(template.id)}
    >
      <CardContent className="p-5 flex flex-col h-full flex-1">
        <div className="flex items-start justify-between gap-4 mb-3">
          <h3 className="font-semibold leading-tight line-clamp-2 text-slate-900" title={template.name}>
            {template.name}
          </h3>
          <div 
            className={`h-2 w-2 rounded-full shrink-0 mt-1.5 ${getStatusColor(template.status)}`}
            title={`Status: ${template.status}`}
          />
        </div>
        
        <div className="mt-auto space-y-3">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="secondary" className={`border-transparent ${getCategoryColor(template.category)}`}>
              {template.category.charAt(0).toUpperCase() + template.category.slice(1)}
            </Badge>
            <div className="flex items-center text-xs text-slate-500 capitalize">
              <VisibilityIcon />
              {template.visibility}
            </div>
          </div>

          {Boolean(template.scope_organization || template.scope_department || template.allowed_roles?.length) && (
            <div className="flex min-w-0 flex-wrap items-center gap-1.5">
              {template.visibility === "organization" && template.scope_organization && (
                <Badge
                  variant="outline"
                  className="max-w-full gap-1 border-indigo-200 bg-indigo-50 font-medium text-indigo-800"
                  title={`Organization: ${template.scope_organization}`}
                >
                  <Building className="h-3 w-3 shrink-0" />
                  <span className="truncate">{template.scope_organization}</span>
                </Badge>
              )}
              {template.visibility === "department" && template.scope_department && (
                <Badge
                  variant="outline"
                  className="max-w-full gap-1 border-teal-200 bg-teal-50 font-medium text-teal-800"
                  title={`Department: ${template.scope_department}${
                    template.scope_organization ? ` (${template.scope_organization})` : ""
                  }`}
                >
                  <Users className="h-3 w-3 shrink-0" />
                  <span className="truncate">{template.scope_department}</span>
                </Badge>
              )}
              {template.allowed_roles?.length ? (
                <Badge
                  variant="outline"
                  className="max-w-full gap-1 border-amber-200 bg-amber-50 font-medium text-amber-800"
                  title={`Only: ${describeRoles(template.allowed_roles)}`}
                >
                  <ShieldCheck className="h-3 w-3 shrink-0" />
                  <span className="truncate">Restricted roles</span>
                </Badge>
              ) : null}
            </div>
          )}
          
          {copyBadge && (
            <Badge
              variant="outline"
              className="max-w-full gap-1 border-violet-200 bg-violet-50 font-medium text-violet-800"
              title={copyBadge}
            >
              <Copy className="h-3 w-3 shrink-0" />
              <span className="truncate">{copyBadge}</span>
            </Badge>
          )}

          <div className="text-xs text-slate-400">
            Uploaded on {formattedDate}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
