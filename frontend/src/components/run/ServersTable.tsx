import type { Server } from "@/api";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

/** Compact read-only server table (new run snapshot, run details). */
export function ServersTable({ servers }: { servers: Server[] }) {
  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>ID</TableHead>
            <TableHead className="text-right">CPU units/tick</TableHead>
            <TableHead className="text-right">Memory (MB)</TableHead>
            <TableHead className="text-right">Rate limit (starts/tick)</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {servers.map((s) => (
            <TableRow key={s.id}>
              <TableCell className="font-mono">{s.id}</TableCell>
              <TableCell className="text-right tabular-nums">{s.cpu_units_per_tick}</TableCell>
              <TableCell className="text-right tabular-nums">{s.mem_mb}</TableCell>
              <TableCell className="text-right tabular-nums">{s.rate_limit_per_sec}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
