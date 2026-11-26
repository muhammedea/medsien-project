import { useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { api, ApiError, type Server } from "@/api";
import { useLoad } from "@/hooks/useLoad";
import { EmptyState, ErrorState, Loading, PageHeader } from "@/components/states";
import { ServerFormDialog } from "@/components/ServerFormDialog";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export function ServersPage() {
  const { data: servers, error, loading, reload } = useLoad(api.listServers, []);
  const [editing, setEditing] = useState<Server | null>(null);
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState<Server | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function confirmDelete() {
    if (!deleting) return;
    try {
      await api.deleteServer(deleting.id);
      setDeleting(null);
      reload();
    } catch (e) {
      setDeleteError((e as ApiError).message);
    }
  }

  return (
    <>
      <PageHeader
        title="Servers"
        description="Changes apply to future runs. Past runs keep the servers they ran with."
        actions={
          <Button onClick={() => setAdding(true)}>
            <Plus aria-hidden /> Add server
          </Button>
        }
      />

      {loading && !servers ? (
        <Loading />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} title="Could not load servers" />
      ) : servers && servers.length === 0 ? (
        <EmptyState message="No servers. Runs need at least one server." />
      ) : (
        servers && (
          <div className="rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead className="text-right">CPU units/tick</TableHead>
                  <TableHead className="text-right">Memory (MB)</TableHead>
                  <TableHead className="text-right">Rate limit (starts/tick)</TableHead>
                  <TableHead className="w-40 text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {servers.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell className="font-mono">{s.id}</TableCell>
                    <TableCell className="text-right tabular-nums">{s.cpu_units_per_tick}</TableCell>
                    <TableCell className="text-right tabular-nums">{s.mem_mb}</TableCell>
                    <TableCell className="text-right tabular-nums">{s.rate_limit_per_sec}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="sm" onClick={() => setEditing(s)} aria-label={`Edit server ${s.id}`}>
                          <Pencil aria-hidden /> Edit
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-destructive"
                          onClick={() => {
                            setDeleteError(null);
                            setDeleting(s);
                          }}
                          aria-label={`Delete server ${s.id}`}
                        >
                          <Trash2 aria-hidden /> Delete
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )
      )}

      <ServerFormDialog
        open={adding || editing !== null}
        server={editing}
        existingIds={(servers ?? []).map((s) => s.id)}
        onClose={() => {
          setAdding(false);
          setEditing(null);
        }}
        onSaved={() => {
          setAdding(false);
          setEditing(null);
          reload();
        }}
      />

      <AlertDialog open={deleting !== null} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete server {deleting?.id}?</AlertDialogTitle>
            <AlertDialogDescription>
              Delete server {deleting?.id}? Future runs will not use it. Past runs aren't affected.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {deleteError && (
            <Alert variant="destructive">
              <AlertDescription>{deleteError}</AlertDescription>
            </Alert>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={(e) => {
                e.preventDefault(); // keep the dialog open until the API answers
                void confirmDelete();
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
