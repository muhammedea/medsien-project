import type { ReactNode } from "react";
import { AlertCircle, Loader2 } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground" role="status">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label}
    </div>
  );
}

export function ErrorState({ error, onRetry, title = "Something went wrong" }: { error: Error; onRetry?: () => void; title?: string }) {
  return (
    <Alert variant="destructive">
      <AlertCircle aria-hidden />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>
        <p>{error.message}</p>
        {onRetry && (
          <Button variant="outline" size="sm" className="mt-2" onClick={onRetry}>
            Try again
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}

export function EmptyState({ message, children }: { message: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed py-12 text-center">
      <p className="text-sm text-muted-foreground">{message}</p>
      {children}
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <div className="mt-1 text-sm text-muted-foreground">{description}</div>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
