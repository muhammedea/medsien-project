import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError, type Server } from "@/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

type Field = keyof Server;
type FormValues = Record<Field, string>;

const NUMBER_FIELDS: { key: Exclude<Field, "id">; label: string; hint: string }[] = [
  { key: "cpu_units_per_tick", label: "CPU units per tick", hint: "Work units processed per tick" },
  { key: "mem_mb", label: "Memory (MB)", hint: "Memory available for running requests" },
  { key: "rate_limit_per_sec", label: "Rate limit (starts per tick)", hint: "Requests that may start per tick" },
];

const EMPTY: FormValues = { id: "", cpu_units_per_tick: "", mem_mb: "", rate_limit_per_sec: "" };

/** Quick hints in the browser. The API is the final judge. */
function check(values: FormValues, isEdit: boolean, existingIds: string[]): Partial<Record<Field, string>> {
  const errors: Partial<Record<Field, string>> = {};
  if (!isEdit) {
    if (!values.id.trim()) errors.id = "ID must not be blank.";
    else if (existingIds.includes(values.id)) errors.id = `A server with ID "${values.id}" already exists.`;
  }
  for (const { key } of NUMBER_FIELDS) {
    const v = values[key].trim();
    if (!/^\d+$/.test(v) || Number(v) < 1) errors[key] = "Must be a whole number of at least 1.";
  }
  return errors;
}

export function ServerFormDialog({
  open,
  server,
  existingIds,
  onClose,
  onSaved,
}: {
  open: boolean;
  server: Server | null; // null = add
  existingIds: string[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = server !== null;
  const [values, setValues] = useState<FormValues>(EMPTY);
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Reset the form each time the dialog opens; Cancel discards the changes.
  useEffect(() => {
    if (!open) return;
    setValues(
      server
        ? {
            id: server.id,
            cpu_units_per_tick: String(server.cpu_units_per_tick),
            mem_mb: String(server.mem_mb),
            rate_limit_per_sec: String(server.rate_limit_per_sec),
          }
        : EMPTY,
    );
    setErrors({});
    setFormError(null);
    setSaving(false);
  }, [open, server]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const hints = check(values, isEdit, existingIds);
    setErrors(hints);
    setFormError(null);
    if (Object.keys(hints).length > 0) return;

    const numbers = {
      cpu_units_per_tick: Number(values.cpu_units_per_tick),
      mem_mb: Number(values.mem_mb),
      rate_limit_per_sec: Number(values.rate_limit_per_sec),
    };
    setSaving(true);
    try {
      if (isEdit) await api.updateServer(server.id, numbers);
      else await api.createServer({ id: values.id, ...numbers });
      onSaved();
    } catch (err) {
      const apiErr = err as ApiError;
      if (apiErr.field && apiErr.field in EMPTY) setErrors({ [apiErr.field]: apiErr.message });
      else setFormError(apiErr.message);
    } finally {
      setSaving(false);
    }
  }

  const fieldProps = (key: Field) => ({
    id: `server-${key}`,
    value: values[key],
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => setValues((v) => ({ ...v, [key]: e.target.value })),
    "aria-invalid": errors[key] ? true : undefined,
    "aria-describedby": `server-${key}-msg`,
  });

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit} noValidate className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{isEdit ? `Edit server ${server.id}` : "Add server"}</DialogTitle>
            <DialogDescription>Changes apply to future runs only.</DialogDescription>
          </DialogHeader>

          {formError && (
            <Alert variant="destructive">
              <AlertDescription>{formError}</AlertDescription>
            </Alert>
          )}

          <div className="grid gap-1.5">
            <Label htmlFor="server-id">ID</Label>
            <Input {...fieldProps("id")} readOnly={isEdit} className={isEdit ? "bg-muted" : undefined} autoFocus={!isEdit} />
            <p id="server-id-msg" className={errors.id ? "text-xs text-destructive" : "text-xs text-muted-foreground"}>
              {errors.id ?? (isEdit ? "The ID can't be changed." : "For example s3.")}
            </p>
          </div>

          {NUMBER_FIELDS.map(({ key, label, hint }) => (
            <div key={key} className="grid gap-1.5">
              <Label htmlFor={`server-${key}`}>{label}</Label>
              <Input {...fieldProps(key)} inputMode="numeric" autoFocus={isEdit && key === "cpu_units_per_tick"} />
              <p
                id={`server-${key}-msg`}
                className={errors[key] ? "text-xs text-destructive" : "text-xs text-muted-foreground"}
              >
                {errors[key] ?? hint}
              </p>
            </div>
          ))}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
