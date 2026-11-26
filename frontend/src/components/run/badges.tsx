import { CheckCircle2, Copy, Loader2, XCircle } from "lucide-react";
import type { Run } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export function StatusBadge({ status }: { status: Run["status"] }) {
  if (status === "completed")
    return (
      <Badge variant="secondary">
        <CheckCircle2 aria-hidden className="text-emerald-600" /> completed
      </Badge>
    );
  if (status === "failed")
    return (
      <Badge variant="destructive">
        <XCircle aria-hidden /> failed
      </Badge>
    );
  return (
    <Badge variant="outline">
      <Loader2 aria-hidden className="animate-spin" /> pending
    </Badge>
  );
}

/** Shows determinism directly: same input_hash + engine_version produced the same trace_hash. */
export function SameOutputBadge({ runId }: { runId: number | null }) {
  if (runId === null) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="outline" className="border-sky-300 bg-sky-50 text-sky-800" tabIndex={0}>
          <Copy aria-hidden /> same output as #{runId}
        </Badge>
      </TooltipTrigger>
      <TooltipContent>
        Same input_hash and engine_version as run #{runId}, and the same trace_hash: the output is byte-identical.
      </TooltipContent>
    </Tooltip>
  );
}
