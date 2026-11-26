import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { Play, Plus } from "lucide-react";
import { api, ApiError, type Run } from "@/api";
import { useLoad } from "@/hooks/useLoad";
import { formatDate, show } from "@/lib/format";
import { EmptyState, ErrorState, Loading, PageHeader } from "@/components/states";
import { SameOutputBadge, StatusBadge } from "@/components/run/badges";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export function RunsPage() {
  const navigate = useNavigate();
  const runs = useLoad(api.listRuns, []);
  const servers = useLoad(api.listServers, []);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const noServers = servers.data !== undefined && servers.data.length === 0;
  const noServersMessage = "No servers. Runs need at least one server.";

  async function runSample() {
    setStarting(true);
    setStartError(null);
    try {
      const run = await api.startRun({});
      navigate(`/runs/${run.id}`);
    } catch (e) {
      setStartError((e as ApiError).message);
      setStarting(false);
    }
  }

  const openRun = (run: Run) => navigate(`/runs/${run.id}`);

  return (
    <>
      <PageHeader
        title="Runs"
        description={
          noServers ? (
            <span>
              {noServersMessage} <Link to="/servers" className="underline">Add one</Link>.
            </span>
          ) : (
            "Every run gets a new number. Click a row for details."
          )
        }
        actions={
          noServers ? (
            <Button disabled title={noServersMessage}>
              <Plus aria-hidden /> New run
            </Button>
          ) : (
            <Button asChild>
              <Link to="/runs/new">
                <Plus aria-hidden /> New run
              </Link>
            </Button>
          )
        }
      />

      {startError && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{startError}</AlertDescription>
        </Alert>
      )}

      {runs.loading && !runs.data ? (
        <Loading />
      ) : runs.error ? (
        <ErrorState error={runs.error} onRetry={runs.reload} title="Could not load runs" />
      ) : runs.data && runs.data.length === 0 ? (
        <EmptyState message="No runs yet.">
          <Button onClick={runSample} disabled={starting || noServers} title={noServers ? noServersMessage : undefined}>
            <Play aria-hidden /> {starting ? "Running…" : "Run the sample"}
          </Button>
          <p className="max-w-md text-xs text-muted-foreground">
            Uses the sample requests, <code>exclusive</code> mode, no limits and the current servers. This reproduces the
            assignment's sample run.
          </p>
        </EmptyState>
      ) : (
        runs.data && (
          <div className="rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-24">#</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Mode</TableHead>
                  <TableHead className="text-right">Requests</TableHead>
                  <TableHead className="text-right">Finished</TableHead>
                  <TableHead className="text-right">Dropped</TableHead>
                  <TableHead className="text-right">Avg wait</TableHead>
                  <TableHead className="text-right">p95 wait</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.data.map((run) => (
                  <TableRow
                    key={run.id}
                    className="cursor-pointer"
                    onClick={() => openRun(run)}
                    onKeyDown={(e) => e.key === "Enter" && openRun(run)}
                    tabIndex={0}
                    aria-label={`Open run ${run.id}`}
                  >
                    <TableCell className="font-medium">#{run.id}</TableCell>
                    <TableCell>{formatDate(run.created_at)}</TableCell>
                    <TableCell>
                      <StatusBadge status={run.status} />
                    </TableCell>
                    <TableCell>{run.config.execution_mode}</TableCell>
                    <TableCell className="text-right tabular-nums">{show(run.summary?.total_requests)}</TableCell>
                    <TableCell className="text-right tabular-nums">{show(run.summary?.finished)}</TableCell>
                    <TableCell className="text-right tabular-nums">{show(run.summary?.dropped)}</TableCell>
                    <TableCell className="text-right tabular-nums">{show(run.summary?.avg_wait_ticks)}</TableCell>
                    <TableCell className="text-right tabular-nums">{show(run.summary?.p95_wait_ticks)}</TableCell>
                    <TableCell>
                      <SameOutputBadge runId={run.same_output_as} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <p className="border-t px-4 py-2 text-xs text-muted-foreground">Wait times are in ticks.</p>
          </div>
        )
      )}
    </>
  );
}
