import { useRef, useState, type DragEvent, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";
import { Download, FileUp, Play, X } from "lucide-react";
import { api, ApiError, urls, type ExecutionMode, type RunConfig } from "@/api";
import { useLoad } from "@/hooks/useLoad";
import { previewCsv, EXPECTED_COLUMNS, type CsvPreview } from "@/lib/csv";
import { formatBytes } from "@/lib/format";
import { ErrorState, Loading, PageHeader } from "@/components/states";
import { ServersTable } from "@/components/run/ServersTable";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "cn";

type Upload = { file: File; preview: CsvPreview };

const MODES: { value: ExecutionMode; label: string; help: string }[] = [
  {
    value: "exclusive",
    label: "exclusive (default)",
    help: "One request per server at a time, using the whole CPU. Passes the provided validate_run.py.",
  },
  {
    value: "shared",
    label: "shared",
    help: "Many requests per server while their memory fits; the CPU is split evenly among them each tick.",
  },
];

/** "" means no limit; otherwise a whole number >= 0. */
function parseLimit(raw: string): { value: number | null; error?: string } {
  const v = raw.trim();
  if (v === "") return { value: null };
  if (!/^\d+$/.test(v)) return { value: null, error: "Must be a whole number of 0 or more, or empty." };
  return { value: Number(v) };
}

function Section({ step, title, description, children }: { step: number; title: string; description?: ReactNode; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="mr-2 text-muted-foreground">{step}.</span>
          {title}
        </CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function NewRunPage() {
  const navigate = useNavigate();
  const servers = useLoad(api.listServers, []);
  const limits = useLoad(api.limits, []);

  const [source, setSource] = useState<"sample" | "upload">("sample");
  const [upload, setUpload] = useState<Upload | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const [mode, setMode] = useState<ExecutionMode>("exclusive");
  const [maxWait, setMaxWait] = useState("");
  const [maxQueue, setMaxQueue] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<ApiError | null>(null);

  const wait = parseLimit(maxWait);
  const queue = parseLimit(maxQueue);

  async function chooseFile(file: File | undefined) {
    setUploadError(null);
    setUpload(null);
    if (!file) return;
    const lim = limits.data;
    if (lim && file.size > lim.max_upload_bytes) {
      setUploadError(`${file.name} is ${formatBytes(file.size)}; the limit is ${formatBytes(lim.max_upload_bytes)}.`);
      return;
    }
    const preview = previewCsv(await file.text());
    if (lim && preview.rowCount > lim.max_request_rows) {
      setUploadError(`${file.name} has ${preview.rowCount.toLocaleString()} rows; the limit is ${lim.max_request_rows.toLocaleString()}.`);
    } else if (preview.missingColumns.length > 0) {
      setUploadError(`Missing columns: ${preview.missingColumns.join(", ")}. Expected ${EXPECTED_COLUMNS.join(",")}.`);
    } else if (preview.rowCount === 0) {
      setUploadError("The file has no request rows.");
    }
    setUpload({ file, preview });
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    setSource("upload");
    void chooseFile(e.dataTransfer.files[0]);
  }

  const noServers = servers.data !== undefined && servers.data.length === 0;
  const canSubmit =
    !submitting &&
    !noServers &&
    !wait.error &&
    !queue.error &&
    (source === "sample" || (upload !== null && uploadError === null));

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setSubmitError(null);
    const config: Partial<RunConfig> = {
      execution_mode: mode,
      max_wait_ticks: wait.value,
      max_queue_length: queue.value,
    };
    try {
      const run = await api.startRun(config, source === "upload" ? upload!.file : undefined, upload?.file.name);
      navigate(`/runs/${run.id}`);
    } catch (err) {
      setSubmitError(err as ApiError);
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-6">
      <PageHeader
        title="New run"
        description="With every default left as is, the run reproduces the assignment's sample run."
        actions={
          <Button type="submit" disabled={!canSubmit}>
            <Play aria-hidden /> {submitting ? "Running…" : "Run simulation"}
          </Button>
        }
      />

      {submitError && (
        <Alert variant="destructive">
          <AlertTitle>
            {submitError.status === 413
              ? "File too large"
              : submitError.field === "requests"
                ? "Invalid requests file"
                : submitError.field === "config"
                  ? "Invalid configuration"
                  : "Could not start the run"}
          </AlertTitle>
          <AlertDescription>{submitError.message}</AlertDescription>
        </Alert>
      )}

      <Section step={1} title="Requests">
        <RadioGroup value={source} onValueChange={(v) => setSource(v as "sample" | "upload")} className="gap-3">
          <div className="flex items-center gap-2">
            <RadioGroupItem value="sample" id="src-sample" />
            <Label htmlFor="src-sample">Use the sample requests</Label>
            <a href={urls.sampleCsv} className="ml-2 inline-flex items-center gap-1 text-xs text-muted-foreground underline">
              <Download className="size-3" aria-hidden /> Download sample CSV
            </a>
          </div>
          <div className="flex items-center gap-2">
            <RadioGroupItem value="upload" id="src-upload" />
            <Label htmlFor="src-upload">Upload a CSV file</Label>
          </div>
        </RadioGroup>

        {source === "upload" && (
          <div className="mt-4 grid gap-3">
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={cn(
                "flex flex-col items-center gap-2 rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors",
                dragging ? "border-primary bg-muted" : "border-border",
              )}
            >
              <FileUp className="size-6 text-muted-foreground" aria-hidden />
              <p className="text-sm">
                Drag and drop a CSV file here, or{" "}
                <Button type="button" variant="link" className="h-auto p-0" onClick={() => fileInput.current?.click()}>
                  choose a file
                </Button>
              </p>
              <p className="text-xs text-muted-foreground">
                Expected format: <code className="font-mono">{EXPECTED_COLUMNS.join(",")}</code>
                {limits.data && (
                  <>
                    {" "}· up to {formatBytes(limits.data.max_upload_bytes)} and{" "}
                    {limits.data.max_request_rows.toLocaleString()} rows
                  </>
                )}
              </p>
              <input
                ref={fileInput}
                type="file"
                accept=".csv,text/csv"
                className="sr-only"
                aria-label="Requests CSV file"
                onChange={(e) => void chooseFile(e.target.files?.[0])}
              />
            </div>

            {uploadError && (
              <Alert variant="destructive">
                <AlertDescription>{uploadError}</AlertDescription>
              </Alert>
            )}

            {upload && (
              <div className="grid gap-2">
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-medium">{upload.file.name}</span>
                  <span className="text-muted-foreground">
                    {formatBytes(upload.file.size)} · {upload.preview.rowCount.toLocaleString()} rows
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-xs"
                    aria-label="Remove file"
                    onClick={() => {
                      setUpload(null);
                      setUploadError(null);
                      if (fileInput.current) fileInput.current.value = "";
                    }}
                  >
                    <X aria-hidden />
                  </Button>
                </div>
                {upload.preview.rows.length > 0 && (
                  <div className="rounded-lg border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          {upload.preview.header.map((h, i) => (
                            <TableHead key={i}>{h}</TableHead>
                          ))}
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {upload.preview.rows.map((row, i) => (
                          <TableRow key={i}>
                            {row.map((cell, j) => (
                              <TableCell key={j} className="font-mono text-xs">
                                {cell}
                              </TableCell>
                            ))}
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                    <p className="border-t px-4 py-2 text-xs text-muted-foreground">
                      Preview of the first {upload.preview.rows.length} rows. The server checks the whole file.
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </Section>

      <Section step={2} title="Configuration">
        <div className="grid gap-6">
          <fieldset className="grid gap-2">
            <legend className="mb-2 text-sm font-medium">Execution mode</legend>
            <RadioGroup value={mode} onValueChange={(v) => setMode(v as ExecutionMode)} className="gap-3">
              {MODES.map((m) => (
                <div key={m.value} className="flex items-start gap-2">
                  <RadioGroupItem value={m.value} id={`mode-${m.value}`} className="mt-0.5" />
                  <div>
                    <Label htmlFor={`mode-${m.value}`} className="font-mono">
                      {m.label}
                    </Label>
                    <p className="text-xs text-muted-foreground">{m.help}</p>
                  </div>
                </div>
              ))}
            </RadioGroup>
          </fieldset>

          <div className="grid max-w-xl grid-cols-2 gap-4">
            {[
              { id: "max-wait", label: "Max wait (ticks)", value: maxWait, set: setMaxWait, parsed: wait },
              { id: "max-queue", label: "Max queue length", value: maxQueue, set: setMaxQueue, parsed: queue },
            ].map((f) => (
              <div key={f.id} className="grid gap-1.5">
                <Label htmlFor={f.id}>{f.label}</Label>
                <Input
                  id={f.id}
                  inputMode="numeric"
                  placeholder="No limit"
                  value={f.value}
                  onChange={(e) => f.set(e.target.value)}
                  aria-invalid={f.parsed.error ? true : undefined}
                  aria-describedby={`${f.id}-msg`}
                />
                <p id={`${f.id}-msg`} className={f.parsed.error ? "text-xs text-destructive" : "text-xs text-muted-foreground"}>
                  {f.parsed.error ?? "Leave empty for no limit."}
                </p>
              </div>
            ))}
          </div>
        </div>
      </Section>

      <Section
        step={3}
        title="Servers used"
        description={
          <>
            This is the snapshot the run will use. <Link to="/servers" className="underline">Edit servers</Link>
          </>
        }
      >
        {servers.loading && !servers.data ? (
          <Loading />
        ) : servers.error ? (
          <ErrorState error={servers.error} onRetry={servers.reload} title="Could not load servers" />
        ) : noServers ? (
          <Alert variant="destructive">
            <AlertDescription>
              No servers. Runs need at least one server. <Link to="/servers" className="underline">Add one</Link>.
            </AlertDescription>
          </Alert>
        ) : (
          servers.data && (
            <>
              <p className="mb-2 text-sm text-muted-foreground">
                {servers.data.length} server{servers.data.length === 1 ? "" : "s"}
              </p>
              <ServersTable servers={servers.data} />
            </>
          )
        )}
      </Section>
    </form>
  );
}
