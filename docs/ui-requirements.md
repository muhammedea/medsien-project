# UI requirements

The dashboard is a single React app with two main sections, **Servers** and **Runs**. It talks only to the backend API described in the [high-level design](high-level-design.md). The assignment says polish isn't graded beyond functionality, so the goal is clear, working screens rather than visual design.

**Priorities:**
- **P0:** required by the assignment.
- **P1:** needed for a good demo and the interview.
- **P2:** bonus.

## 1. Navigation

| Route | Screen | Priority |
| --- | --- | --- |
| `/servers` | Server list with add, edit and delete | P0 |
| `/runs` | Run history | P0 |
| `/runs/new` | Start a new run (choose requests and config) | P0 |
| `/runs/:id` | Run details: summary, events, visualization | P0 (visualization P2) |

- A top bar holds the app name and the two menu items, **Servers** and **Runs**.
- `/` redirects to `/runs`.
- Every screen that loads data shows a loading state, an empty state and an error state that includes the API's error message.

## 2. Servers

### 2.1 Server list (P0)

- A table with one row per server, sorted by id. Columns: **ID**, **CPU units/tick**, **Memory (MB)**, **Rate limit (starts/tick)**, and actions (**Edit**, **Delete**).
- An **Add server** button above the table.
- A note above the table: "Changes apply to future runs. Past runs keep the servers they ran with."
- **Empty state:** "No servers. Runs need at least one server." The **New run** button on the Runs screen is disabled, with the same explanation.

### 2.2 Add and edit server (P0)

- The form opens in a dialog with fields `id`, `cpu_units_per_tick`, `mem_mb` and `rate_limit_per_sec`.
- **Edit:** the `id` field is read-only, because the API doesn't allow changing it.
- **Checks in the browser**, as quick hints only:
  - `id` must not be blank or a duplicate;
  - the three numbers must be whole numbers of at least 1.
- **The API is the final judge:** a `422` response is shown next to the field it concerns, or at the top of the form.
- **Save** closes the dialog and refreshes the table. **Cancel** discards the changes.

### 2.3 Delete server (P0)

- Deleting asks for confirmation first: "Delete server s2? Future runs will not use it."
- Past runs aren't affected.

## 3. Runs

### 3.1 Run history (P0)

- A table of past runs, newest first. Columns:
  - **#** (run id), **Created**, **Status** (`completed` / `failed`), **Mode**;
  - **Requests**, **Finished**, **Dropped**, **Avg wait**, **p95 wait** (in ticks).
- Clicking a row opens the run details.
- A **New run** button.
- **Empty state (no runs yet):** "No runs yet." with a **Run the sample** button, which starts a run with all the defaults from §3.2 without opening the form.
- **P1:** a "same output as #n" badge when the run has the same `input_hash`, `engine_version` and `trace_hash` as an earlier run. This shows determinism directly in the UI.

### 3.2 New run (P0)

The screen has three sections and a **Run simulation** button.

1. **Requests**
   - A choice between **Use the sample requests** and **Upload a CSV file**. **The sample is selected by default.**
   - With every default left as is (sample requests, `exclusive` mode, no limits, the seeded servers), pressing **Run simulation** reproduces the assignment's sample run. The resulting `run.jsonl` passes `validate_run.py`. A reviewer can check the core requirement with one click.
   - **Upload:**
     - Choose a file, or drag and drop it (P1).
     - Shows the file name, its size, and a preview of the first 10 rows parsed in the browser.
     - The expected format is shown: `t,request_id,work_units,mem_mb`.
     - A **Download sample CSV** link.
   - Size and row limits are checked in the browser for quick feedback. The API repeats the checks and returns `413` if a file is too large.
2. **Configuration**
   - **Execution mode:** `exclusive` (default) or `shared`, each with a one-line explanation.
   - **Max wait (ticks)** and **Max queue length:** whole numbers of 0 or more. Leaving a field empty means no limit, and a hint says so.
   - P2: **Placement strategy.** Hidden while only `earliest_finish` exists.
3. **Servers used**
   - A read-only summary of the current servers (count and a compact table), with a link to **Servers** for edits.
   - This is the snapshot the run will use.

Pressing **Run simulation** sends `POST /api/runs`.
- **Success:** the app goes to `/runs/:id`.
- **Error:** the message is shown on this screen. A `422` for an invalid CSV includes the line number from the engine's error.

### 3.3 Run details (P0)

- **Header:**
  - run number, status, creation time, mode and the other config values;
  - `engine_version`;
  - a shortened `input_hash` and `trace_hash`.
- **Actions:**
  - **Download run.jsonl** (P0);
  - download the saved inputs: `servers.json`, `requests.csv`, `config.json` (P1);
  - **Run again with the same inputs** (P1). This calls `POST /api/runs/{id}/rerun`, which makes a new run from the saved snapshot (not the current servers), so it shows the "same output" badge.
- **Summary cards:** total requests, started, finished, dropped (split by reason), average, p50, p95 and max wait, and the last tick.
- **Servers used:** the server snapshot of this run.
- **Events table:**
  - one row per line of `run.jsonl`, with columns `t`, `event`, `request_id`, `server_id`, `reason`;
  - filters for event type, request id and server id;
  - paginated (P0 shows the table; filters are P1);
  - served by `GET /api/runs/{id}/events`, which filters and paginates on the backend.
- **Visualization** (P2, recommended): see §4.

## 4. Recommended visualization (P2)

Three linked views on the run details screen. Together they cover the questions an interviewer is likely to ask: where did each request run, why did it wait, and what happened during overload?

### 4.1 Server timeline (Gantt chart)

- **Layout:**
  - one horizontal lane per server, sorted by id;
  - the x-axis is ticks, and each request is a bar from its start to its finish tick;
  - hovering over a bar shows the request id, work units, memory, arrival, start, finish and wait time.
- **`exclusive` mode:** one row per lane, and bars never overlap.
- **`shared` mode:** overlapping bars are stacked into sub-rows within the lane. Bars are placed by start tick and request id, so the layout is always the same.
- **Queue lane:** an extra lane at the top shows waiting time as a thin line from arrival to start. Drops are marked with an ✕, colored by reason (`no_server_fits`, `max_wait_exceeded`, `queue_full`).
- **Interaction:** zoom and pan along the time axis. Clicking a bar highlights the request in the events table.

### 4.2 Tick inspector

- A slider, plus step buttons (◀ ▶), selects a tick `t`.
- For that tick, it shows:
  - **each server:** the running requests, a bar for memory used out of `mem_mb`, and starts this tick out of `rate_limit_per_sec`;
  - **the queue:** the requests waiting, oldest first;
  - **the events logged at `t`**, in the order they were written.
- The selected tick appears as a vertical line in the timeline and the chart.
- This is the most direct way to explain a scheduling decision during the interview.

### 4.3 Load over time

A line chart over ticks with:
- the number of waiting requests;
- the number of running requests;
- total drops so far.

P2+: a small per-server chart of memory use.

### 4.4 Data source

The backend works out the visualization data from the saved files, through **`GET /api/runs/{id}/timeline`**. The browser doesn't re-read `run.jsonl` itself. Reasons:
- The memory and work-unit values the views need come from the saved inputs, which the backend already has.
- The derivation is written once in Python and can be tested against the trace.
- The data only lists the ticks where something changes, so large runs stay small.

Proposed response:

```json
{
  "mode": "shared",
  "first_tick": 0,
  "last_tick": 42,
  "initial_view": {"start": 0, "end": 42},
  "servers": [{"id": "s1", "cpu_units_per_tick": 10, "mem_mb": 1024, "rate_limit_per_sec": 2}],
  "requests": [
    {"id": "r1", "arrival": 0, "work_units": 20, "mem_mb": 200,
     "server_id": "s1", "start": 0, "finish": 2, "drop_t": null, "drop_reason": null}
  ],
  "series": [
    {"t": 0, "queued": 0, "running": 2, "dropped_total": 0, "mem_used": {"s1": 200, "s2": 100}}
  ]
}
```

- `series` only has an entry for ticks where a value changed. Between entries, the value stays the same.
- `series[i]` is the state after all events of tick `t`. Requests are listed in arrival order `(t, CSV row)`.
- For large runs (more than `TIMELINE_ZOOM_THRESHOLD` requests, default 2,000), `initial_view` covers the ticks of the first 2,000 arrivals and the Gantt chart starts zoomed in on it. Otherwise it is the whole run. The chart and the tick inspector work at any size.
- The tick inspector's "events logged at `t`" come from `GET /api/runs/{id}/events?t=…`.

**Rendering:**
- the Gantt chart and tick inspector in plain SVG;
- the line chart with a small chart library (Recharts).

There's no other visualization dependency.

## 5. Other requirements

- **Stack:** React with React Router, and `fetch` through a small typed API client (`src/api.ts`). No global state library is needed; each screen loads its own data.
- **Layout:** desktop first; a screen width of 1280 px or more is enough.
- **Components:** shadcn/ui (Radix + Tailwind CSS v4), lucide icons.
- **Accessibility:** form fields have labels, keyboard navigation works in dialogs, and colors aren't the only way meaning is shown (drops also use the ✕ symbol).
- **No authentication.** It's a local, single-user tool.
- **Numbers shown exactly as the API returns them.** Wait times are in ticks, and only averages are rounded, as the backend already does.

## 6. Backend changes this requires

The [high-level design](high-level-design.md) API table already includes these:
- `GET /api/runs/{id}/timeline`: visualization data (§4.4);
- `GET /api/runs/{id}/inputs/{name}`: download a saved input file (`servers.json`, `requests.csv`, `config.json`);
- `GET /api/samples/requests.csv`: the sample CSV, as a template.
