import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { api, EVENT_TYPES, type EventFilters } from "@/api";
import { useLoad } from "@/hooks/useLoad";
import { DROP_COLORS } from "@/lib/timeline";
import { ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const PAGE_SIZE = 50;
const ALL = "__all__";

/** One row per line of run.jsonl, filtered and paginated by the API. */
export function EventsTable({
  runId,
  serverIds,
  requestFilter,
  onRequestFilterChange,
}: {
  runId: number;
  serverIds: string[];
  requestFilter: string;
  onRequestFilterChange: (id: string) => void;
}) {
  const [event, setEvent] = useState("");
  const [serverId, setServerId] = useState("");
  const [requestInput, setRequestInput] = useState(requestFilter);
  const [page, setPage] = useState(0);

  // The request filter can also be set from outside (clicking a bar in the timeline).
  useEffect(() => {
    setRequestInput(requestFilter);
    setPage(0);
  }, [requestFilter]);

  // Apply typed request ids after a short pause.
  useEffect(() => {
    const h = setTimeout(() => {
      if (requestInput.trim() !== requestFilter) onRequestFilterChange(requestInput.trim());
    }, 300);
    return () => clearTimeout(h);
  }, [requestInput, requestFilter, onRequestFilterChange]);

  const filters: EventFilters = { event, server_id: serverId, request_id: requestFilter };
  const { data, error, loading, reload } = useLoad(
    () => api.events(runId, page * PAGE_SIZE, PAGE_SIZE, filters),
    [runId, page, event, serverId, requestFilter],
  );
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const filtered = event !== "" || serverId !== "" || requestFilter !== "";

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-end gap-3">
        <div className="grid gap-1.5">
          <Label htmlFor="ev-type">Event type</Label>
          <Select
            value={event || ALL}
            onValueChange={(v) => {
              setEvent(v === ALL ? "" : v);
              setPage(0);
            }}
          >
            <SelectTrigger id="ev-type" className="w-52">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All events</SelectItem>
              {EVENT_TYPES.map((t) => (
                <SelectItem key={t} value={t}>
                  {t}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="ev-request">Request id</Label>
          <Input id="ev-request" className="w-40" placeholder="any" value={requestInput} onChange={(e) => setRequestInput(e.target.value)} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="ev-server">Server id</Label>
          <Select
            value={serverId || ALL}
            onValueChange={(v) => {
              setServerId(v === ALL ? "" : v);
              setPage(0);
            }}
          >
            <SelectTrigger id="ev-server" className="w-36">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>Any server</SelectItem>
              {serverIds.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {filtered && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setEvent("");
              setServerId("");
              onRequestFilterChange("");
              setPage(0);
            }}
          >
            <X aria-hidden /> Clear filters
          </Button>
        )}
      </div>

      {error ? (
        <ErrorState error={error} onRetry={reload} title="Could not load events" />
      ) : !data ? (
        <Loading />
      ) : (
        <>
          <div className="rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-16 text-right">Line</TableHead>
                  <TableHead className="w-20 text-right">t</TableHead>
                  <TableHead>event</TableHead>
                  <TableHead>request_id</TableHead>
                  <TableHead>server_id</TableHead>
                  <TableHead>reason</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody className={loading ? "opacity-60" : undefined}>
                {data.items.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                      No events match these filters.
                    </TableCell>
                  </TableRow>
                ) : (
                  data.items.map((e) => (
                    <TableRow key={e.line}>
                      <TableCell className="text-right text-muted-foreground tabular-nums">{e.line}</TableCell>
                      <TableCell className="text-right tabular-nums">{e.t}</TableCell>
                      <TableCell className="font-mono text-xs">{e.event}</TableCell>
                      <TableCell className="font-mono">
                        <button type="button" className="hover:underline" onClick={() => onRequestFilterChange(e.request_id)}>
                          {e.request_id}
                        </button>
                      </TableCell>
                      <TableCell className="font-mono">{e.server_id ?? ""}</TableCell>
                      <TableCell>
                        {e.reason && (
                          <span className="inline-flex items-center gap-1">
                            <span style={{ color: DROP_COLORS[e.reason] }} className="font-bold" aria-hidden>
                              ✕
                            </span>
                            {e.reason}
                          </span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {data.total.toLocaleString()} event{data.total === 1 ? "" : "s"}
              {filtered && " match"}
            </span>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => setPage((p) => p - 1)} disabled={page === 0} aria-label="Previous page">
                <ChevronLeft aria-hidden />
              </Button>
              <span className="tabular-nums">
                Page {page + 1} of {pages}
              </span>
              <Button variant="outline" size="sm" onClick={() => setPage((p) => p + 1)} disabled={page + 1 >= pages} aria-label="Next page">
                <ChevronRight aria-hidden />
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
