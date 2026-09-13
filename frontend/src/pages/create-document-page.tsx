import { useEffect, useMemo, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ApiError, DocumentFormValues, TemplateField, TemplateResponse, templatesApi } from "@/lib/api";
import { applyValidationRule } from "@/lib/validation";
import { useAuth } from "@/context/auth-context";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Form, FormField } from "@/components/ui/form";
import { DynamicField } from "@/components/forms/DynamicField";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, FileText } from "lucide-react";

/**
 * Builds a dynamic Zod schema from template fields.
 * Each field becomes a form entry keyed by field_name.
 */
function buildFormSchema(fields: TemplateField[]) {
  const shape: Record<string, z.ZodTypeAny> = {};

  for (const field of fields) {
    const fieldLabel = field.field_label || field.field_name;
    let schema: z.ZodTypeAny;

    switch (field.field_type) {
      case "text":
      case "textarea": {
        let stringSchema = z.string();
        if (field.is_required) {
          stringSchema = stringSchema.min(1, `${fieldLabel} is required`);
        }
        stringSchema = applyValidationRule(stringSchema, field.validation_rule, fieldLabel) as z.ZodString;
        schema = field.is_required ? stringSchema : stringSchema.optional();
        break;
      }

      case "date": {
        let dateSchema = z.string();
        if (field.is_required) {
          dateSchema = dateSchema.min(1, `${fieldLabel} is required`);
        }
        schema = field.is_required ? dateSchema : dateSchema.optional();
        break;
      }

      case "number": {
        let numberSchema: z.ZodNumber;
        if (field.is_required) {
          numberSchema = z.coerce.number({
            required_error: `${fieldLabel} is required`,
            invalid_type_error: `${fieldLabel} must be a number`,
          });
        } else {
          numberSchema = z.coerce.number();
        }
        numberSchema = applyValidationRule(numberSchema, field.validation_rule, fieldLabel) as z.ZodNumber;
        schema = field.is_required ? numberSchema : numberSchema.optional();
        break;
      }

      case "list": {
        let listSchema = z.array(z.string());
        if (field.is_required) {
          listSchema = listSchema.min(1, `${fieldLabel} must have at least one item`);
        }
        listSchema = applyValidationRule(listSchema, field.validation_rule, fieldLabel) as z.ZodArray<any>;
        schema = field.is_required ? listSchema : listSchema.optional();
        break;
      }

      case "signature":
        // Phase 1: stub field, will be file path or upload in V1.10
        schema = z.string().optional();
        break;

      default:
        schema = z.string().optional();
    }

    shape[field.field_name] = schema;
  }

  return z.object(shape);
}

/**
 * Groups fields by section, preserving display_order within each section.
 * Returns sections in the order they first appear.
 */
function groupFieldsBySection(fields: TemplateField[]): Array<{ section: string; fields: TemplateField[] }> {
  const sectionMap = new Map<string, TemplateField[]>();
  const sectionOrder: string[] = [];

  for (const field of fields) {
    const section = field.section || "General Information";
    if (!sectionMap.has(section)) {
      sectionMap.set(section, []);
      sectionOrder.push(section);
    }
    sectionMap.get(section)!.push(field);
  }

  return sectionOrder.map((section) => ({
    section,
    fields: sectionMap.get(section)!,
  }));
}

export default function CreateDocumentPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const token = localStorage.getItem("templateos_access_token") || "";

  const templateId = searchParams.get("template_id");

  const [template, setTemplate] = useState<TemplateResponse | null>(null);
  const [fields, setFields] = useState<TemplateField[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Build dynamic schema from fields
  const formSchema = useMemo(() => {
    if (fields.length === 0) return z.object({});
    return buildFormSchema(fields);
  }, [fields]);

  // Default values from field metadata
  const defaultValues = useMemo(() => {
    const values: DocumentFormValues = {};
    for (const field of fields) {
      if (field.field_type === "list") {
        values[field.field_name] = field.default_value ? JSON.parse(field.default_value) : [];
      } else {
        values[field.field_name] = field.default_value || "";
      }
    }
    return values;
  }, [fields]);

  const form = useForm<DocumentFormValues>({
    resolver: zodResolver(formSchema),
    defaultValues,
  });

  // Reset form when default values change (after fields load)
  useEffect(() => {
    form.reset(defaultValues);
  }, [defaultValues, form]);

  // Fetch template and fields
  useEffect(() => {
    if (!templateId) {
      setError("No template selected. Please provide a template_id.");
      setLoading(false);
      return;
    }

    const fetchData = async () => {
      try {
        setLoading(true);
        setError(null);

        const [templateData, fieldsData] = await Promise.all([
          templatesApi.getTemplateDetail(token, parseInt(templateId, 10)),
          templatesApi.getFields(token, parseInt(templateId, 10)),
        ]);

        setTemplate(templateData);
        setFields(fieldsData);
      } catch (err) {
        if (err instanceof ApiError) {
          if (err.status === 403) {
            setError("You do not have access to this template.");
          } else if (err.status === 404) {
            setError("Template not found.");
          } else {
            setError(err.message);
          }
        } else {
          setError("Failed to load template. Please try again.");
        }
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [templateId, token]);

  // Group fields by section
  const groupedFields = useMemo(() => {
    return groupFieldsBySection(fields);
  }, [fields]);

  // Form submission (Phase 2 placeholder)
  const onSubmit = (values: DocumentFormValues) => {
    console.log("Form values (Phase 2 will save):", values);
    alert("Draft saving will be implemented in Phase 2. Your form data is valid!");
  };

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-4xl">
        <Skeleton className="h-10 w-64 mb-4" />
        <Skeleton className="h-6 w-96 mb-8" />
        <div className="space-y-6">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-4xl">
        <Card className="border-destructive">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-destructive">
              <AlertCircle className="h-5 w-5" />
              Error Loading Template
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground mb-4">{error}</p>
            <Button onClick={() => navigate("/templates")} variant="outline">
              Back to Templates
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!template || fields.length === 0) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-4xl">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              No Fields Configured
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground mb-4">
              This template does not have any configured fields yet.
            </p>
            <Button onClick={() => navigate("/templates")} variant="outline">
              Back to Templates
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight mb-2">
          {template.name}
        </h1>
        {template.description && (
          <p className="text-muted-foreground">{template.description}</p>
        )}
        <p className="text-sm text-muted-foreground mt-2">
          Fill out the form below to create a document from this template.
        </p>
      </div>

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
          {groupedFields.map(({ section, fields: sectionFields }) => (
            <Card key={section}>
              <CardHeader>
                <CardTitle className="text-xl">{section}</CardTitle>
                <CardDescription>
                  {sectionFields.filter((f) => f.is_required).length > 0 && (
                    <span className="text-destructive">* Required fields</span>
                  )}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {sectionFields.map((field) => (
                  <FormField
                    key={field.id}
                    control={form.control}
                    name={field.field_name}
                    render={({ field: formField }) => (
                      <DynamicField field={field} formField={formField} />
                    )}
                  />
                ))}
              </CardContent>
            </Card>
          ))}

          <div className="flex justify-end gap-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate("/templates")}
            >
              Cancel
            </Button>
            <Button type="submit">
              Save Draft
            </Button>
          </div>
        </form>
      </Form>
    </div>
  );
}
