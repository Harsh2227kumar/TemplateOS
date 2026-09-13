import { TemplateField } from "@/lib/api";
import { FormControl, FormDescription, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ListInput } from "./ListInput";
import { ControllerRenderProps } from "react-hook-form";

interface DynamicFieldProps {
  field: TemplateField;
  formField: ControllerRenderProps<any, string>;
}

export function DynamicField({ field, formField }: DynamicFieldProps) {
  const label = field.field_label || field.field_name;
  const placeholder = field.example_value || undefined;

  const renderInput = () => {
    switch (field.field_type) {
      case "text":
        return (
          <Input
            {...formField}
            type="text"
            placeholder={placeholder}
          />
        );

      case "textarea":
        return (
          <Textarea
            {...formField}
            placeholder={placeholder}
            rows={4}
          />
        );

      case "date":
        return (
          <Input
            {...formField}
            type="date"
          />
        );

      case "number":
        return (
          <Input
            {...formField}
            type="number"
            placeholder={placeholder}
            onChange={(e) => {
              const value = e.target.value;
              formField.onChange(value === "" ? "" : parseFloat(value));
            }}
          />
        );

      case "list":
        return (
          <ListInput
            value={formField.value || []}
            onChange={formField.onChange}
            placeholder={placeholder}
          />
        );

      case "signature":
        return (
          <Input
            type="file"
            accept="image/*"
            disabled
            title="Signature support coming in V1.10"
            className="cursor-not-allowed opacity-50"
          />
        );

      default:
        return (
          <Input
            {...formField}
            type="text"
            placeholder={placeholder}
          />
        );
    }
  };

  return (
    <FormItem>
      <FormLabel>
        {label}
        {field.is_required && <span className="text-destructive ml-1">*</span>}
      </FormLabel>
      <FormControl>{renderInput()}</FormControl>
      {field.description && (
        <FormDescription>{field.description}</FormDescription>
      )}
      {field.example_value && !field.description && (
        <FormDescription>Example: {field.example_value}</FormDescription>
      )}
      <FormMessage />
    </FormItem>
  );
}
