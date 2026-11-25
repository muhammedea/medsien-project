# Engine Design

This document describes the simulation engine and its command-line tool: the part that turns `servers.json` + `requests.csv` + a configuration into `run.jsonl`. The API and dashboard are covered elsewhere.

## 1. Goals and scope

- **Deterministic:** the same servers, requests and configuration always produce a byte-identical `run.jsonl`.
- **Validator-compatible by default:** the default mode passes the provided `validate_run.py` unchanged.
- **Swappable execution model:** `exclusive` (default) and `shared` (spec Section 4), selected by configuration.
- **Pure library:** the engine uses only the Python standard library and does no I/O in its core. The CLI, the API and the tests all call the same `simulate()` function.

Out of scope for now (optional features, planned for later): extra placement strategies, auto-scaling, metrics dashboards.

## 2. Terminology

| Term | Meaning |
|---|---|
| Tick | One discrete time step (1 tick = 1 second). Ticks are integers starting at 0. |
| Server | A configuration record: `id`, `cpu_units_per_tick`, `mem_mb`, `rate_limit_per_sec`. Nothing actually runs. |
| Request | A row of `requests.csv`: arrival tick `t`, `request_id`, `work_units`, `mem_mb`. |
| Queue | Requests that have arrived but have neither started nor been dropped. |
| Execution model | The rules for how a server runs requests: how many at once and how CPU is shared. |
| Placement strategy | The rule for picking a server when more than one can accept a request. |

## 3. Execution models

Both models share these rules:
- Memory is reserved from start to finish.
- At most `rate_limit_per_sec` requests start per server per tick.
- A request never moves to another server or gets interrupted.

### 3.1 `exclusive` (default)

- A server runs **at most one request at a time**, and that request gets the whole CPU.
- A server accepts a request if it is idle and `request.mem_mb <= server.mem_mb`.
- Runtime: `ceil(work_units / cpu_units_per_tick)` ticks. A request started at `t` finishes at `t + runtime`.
- This is the model `validate_run.py` checks. Medsien confirmed it should be the default.
- The rate limit can never be reached here, because a busy server can't start anything else. It is still enforced, so the same code works for both models.

### 3.2 `shared` (spec Section 4)

- A server runs **any number of requests at once**, as long as the memory reserved by all of them fits within `mem_mb`.
- A server accepts a request if `mem_used + request.mem_mb <= server.mem_mb` and fewer than `rate_limit_per_sec` requests have started on it this tick.
- **CPU split:** in each tick, every running request on a server gets exactly `cpu_units_per_tick / N`, where N is the number of requests running during that tick. The math uses `fractions.Fraction`, so there is no floating-point drift.
- **No reuse of leftover CPU:** if a request needs less than its share in its last tick, the rest of that share is unused that tick. This follows the spec's "distributes evenly" wording.
- A request finishes once its remaining work is `<= 0`.
- A request that starts at tick `t` counts toward N from tick `t` onward. So a request alone on a server finishes at exactly the same tick in both models.
- The provided validator rejects `shared` traces (overlapping runs, finish times that assume full CPU). A `--mode shared` option for the validator is planned (see §10).

### 3.3 Implementation note

Both models use the same `advance()` logic: subtract `cpu / N` from each running request. `exclusive` is just `shared` with a limit of one running request per server. They are separate classes behind one interface so the difference is easy to see and to extend.

## 4. The tick loop

At tick `t`, the engine runs these steps in this order:

```
1. ARRIVALS
   For each request with arrival == t, in CSV row order:
     log REQUEST_ARRIVED
     if no server could ever hold it (mem_mb > every server's mem_mb):
         log REQUEST_DROPPED (reason "no_server_fits")
     else:
         append it to the end of the queue

2. PROGRESS + FINISHES        (work done during tick t-1)
   For each server, sorted by server_id:
     apply one tick of CPU to every request that was running during t-1
     for requests with remaining <= 0, sorted by request_id:
         log REQUEST_FINISHED, free their memory

3. SCHEDULING                 (FIFO with skip-ahead)
   reset each server's starts_this_tick to 0
   For each queued request, oldest first:
     candidates = servers that accept it now (execution model + rate limit)
     if there are candidates:
         server = placement.choose(request, candidates)
         log REQUEST_STARTED, reserve memory, starts_this_tick += 1
     else if max_wait_ticks is set and t - arrival >= max_wait_ticks:
         log REQUEST_DROPPED (reason "max_wait_exceeded")
     else:
         leave it in the queue          (later requests may still start)
   if max_queue_length is set and the queue is longer than that:
     drop the newest requests until it fits: log REQUEST_DROPPED (reason "queue_full")
```

Why this order:
- **Finishes before starts:** memory and CPU freed at `t` can be used by requests starting at `t`. The provided example does this (r2 finishes and r4 starts on s2 at t=2).
- **Arrivals before scheduling:** a request can start at its own arrival tick.
- **Progress, then finishes:** an event at `t` describes the state after tick `t-1` has been processed, as the spec's PS says. A request started at `t` first gets CPU during tick `t` and is first checked for completion at `t+1`.

**Fast-forward:** when nothing is running and the queue is empty, the loop jumps straight to the next arrival tick. This changes no output; it only skips ticks where nothing happens.

**Termination:** the loop stops when every request has arrived and the queue and all servers are empty. It always stops: every running request gets a positive CPU share each tick, and every queued request either fits some server (which eventually becomes free) or was dropped at arrival.

## 5. Scheduling policy

### 5.1 Queue order: FIFO with skip-ahead

- The queue is ordered by `(arrival tick, CSV row index)`.
- Each tick it is scanned oldest first. A request that can't be placed stays where it is, and requests behind it are still considered.
- **Why:** strict FIFO lets one large request leave the whole cluster idle. For example, a request needing 900 MB waits for s1 while s2 sits empty, and everything behind it waits too.
- **Trade-off:** a large request can wait a long time while a stream of small requests keeps passing it. `max_wait_ticks` puts an upper limit on that wait by dropping the request. Wait times are visible in the summary.

### 5.2 Placement: earliest finish

Among the servers that can accept the request **now**, pick the one with the smallest estimated runtime. Ties go to the smallest `server_id`.

| Model | Estimated runtime on server S |
|---|---|
| exclusive | `ceil(work_units / cpu)` |
| shared | `ceil(work_units * (N + 1) / cpu)`, where N is the number of requests currently running on S |

- The shared estimate assumes the current load stays the same. It is a heuristic, not a promise.
- The engine never holds a request back to wait for a faster server that is busy. It only places requests on servers that can take them right now.
- Placement sits behind a `PlacementStrategy` interface, so more strategies (least loaded, first fit, round robin) can be added later without changing the loop.

## 6. Overload policy

| Situation | Behavior | Drop reason |
|---|---|---|
| The request's `mem_mb` is larger than every server's `mem_mb` | Dropped at arrival, never queued | `no_server_fits` |
| The request has waited `max_wait_ticks` and still can't be placed | Dropped during scheduling | `max_wait_exceeded` |
| The queue is longer than `max_queue_length` after scheduling | Newest requests dropped first (tail drop) | `queue_full` |

- Both limits are **off by default**, giving an unbounded queue. That way the sample data produces the expected trace with no drops.
- `max_wait_ticks = 0` means "start at arrival or drop".
- The queue-length check runs after scheduling. A request that arrives while the queue is full can still start if a server is free.
- `REQUEST_DROPPED` events carry an extra `reason` field. The validator ignores fields it doesn't know.

## 7. Determinism

- **Fixed orders:**
  - requests by `(t, CSV row index)`;
  - servers by `server_id`, compared as plain strings, so `"s10" < "s2"`;
  - finishes within one server by `request_id`.
- **No floats:** `exclusive` uses integers only and `shared` uses `Fraction`.
- **No hidden sources of variation:**
  - no iteration over sets, and dicts are only iterated in insertion order;
  - no clocks, no randomness, no threads.
- **Stable output format:**
  - one compact JSON object per line (`separators=(",", ":")`), with keys in a fixed order: `t`, `event`, `request_id`, `server_id`, `reason`;
  - events in the order they are produced (§4);
  - each line ends with `\n`, UTF-8, no blank lines.
- **Re-runs:** the CLI overwrites the output file on every run. Versioned runs are handled by the API layer.

## 8. Input handling

| Input | Rule |
|---|---|
| `servers.json` | Must contain `servers` (non-empty) and unique ids. If present, `tick_seconds` must be 1. `cpu_units_per_tick >= 1`, `mem_mb >= 1`, `rate_limit_per_sec >= 1`. |
| `requests.csv` | Must have the columns `t, request_id, work_units, mem_mb`. Ids are unique. `t >= 0`, `work_units >= 1`, `mem_mb >= 0`. Rows may be in any order; the engine sorts by `t` and keeps row order within the same tick. |

- Invalid input fails fast with a clear error message (exit code 1). The engine never produces a partial or misleading trace.
- `work_units = 0` is rejected on purpose. That request would start and finish in the same tick, and the validator's alphabetical event sort would then report it as finished before it started.

## 9. Code structure

```
backend/
  pyproject.toml
  engine/
    __init__.py          # public API: simulate(), load_servers(), load_requests()
    models.py            # frozen dataclasses: ServerSpec, RequestSpec, SimulationConfig, Event
    loaders.py           # parse + validate servers.json / requests.csv (InputError)
    simulator.py         # the tick loop, queue, overload policy, event log
    execution.py         # ExecutionModel interface, ExclusiveModel, SharedModel
    placement.py         # PlacementStrategy interface, EarliestFinish
    output.py            # serialize events to JSONL
    cli.py               # python -m engine.cli ...
  validator/
    validate_run.py      # copy of the provided validator (extended later for shared mode)
  tests/
```

The main interfaces:

```python
class ExecutionModel(Protocol):
    def can_accept(self, server: ServerState, req: RequestSpec) -> bool: ...  # capacity only; rate limit checked by the simulator
    def advance(self, server: ServerState) -> list[RunningRequest]: ...      # apply one tick of CPU, return finished requests
    def estimate_runtime(self, server: ServerState, req: RequestSpec) -> int: ...

class PlacementStrategy(Protocol):
    def choose(self, req: RequestSpec, candidates: list[ServerState], model: ExecutionModel) -> ServerState: ...

def simulate(servers: list[ServerSpec], requests: list[RequestSpec], config: SimulationConfig) -> SimulationResult: ...
    # SimulationResult = events + summary (counts, waits, drops by reason)
```

```python
@dataclass(frozen=True)
class SimulationConfig:
    execution_mode: Literal["exclusive", "shared"] = "exclusive"
    placement: Literal["earliest_finish"] = "earliest_finish"
    max_wait_ticks: int | None = None
    max_queue_length: int | None = None
```

### CLI

```
python -m engine.cli \
  --servers servers.json --requests requests.csv --out run.jsonl \
  [--config config.json] [--mode exclusive|shared] [--max-wait N] [--max-queue N]
```

- `--config` takes a JSON file with the `SimulationConfig` fields. Command-line flags override it.
- After the run, the CLI prints a summary: totals, started, finished, dropped by reason, and average, p50, p95 and max wait.
- Exit codes: 0 = success, 1 = invalid input.

## 10. Testing and verification

1. **Golden test:** the sample data in `exclusive` mode produces the same set of events as `project-info/run.jsonl` (see §11).
2. **Validator test:** random inputs from a fixed seed, including overload cases, run in `exclusive` mode, and every result must pass the unmodified `validate_run.py`.
3. **Determinism test:** running twice gives byte-identical output.
4. **Unit tests:**
   - rate limit in `shared` mode;
   - every drop reason;
   - skip-ahead behavior;
   - ties between servers;
   - Fraction math in the CPU split (for example 10 CPU across 3 requests);
   - fast-forward over idle gaps;
   - input validation errors.
5. **Validator for shared mode:** add `--mode shared` to `validate_run.py`. It replays the trace with the §3.2 rules and checks finish times and total memory per tick. Without the flag, the validator behaves exactly as the original. It will be written separately from the engine code, so the engine doesn't end up checking itself.

## 11. Worked example (sample data, exclusive mode)

The servers are s1 (10 CPU, 1024 MB, rate limit 2) and s2 (5 CPU, 512 MB, rate limit 1).

| t | Step | What happens |
|---|---|---|
| 0 | Arrivals | r1 (20 work units, 200 MB) and r2 (10, 100) are queued. |
| 0 | Scheduling | r1: s1 gives 2 ticks, s2 gives 4, so **s1**. r2: only s2 is free (2 ticks), so **s2**. |
| 1 | Arrivals | r3 (15, 300) is queued. Both servers are busy, so it waits. |
| 2 | Arrivals | r4 (5, 100) is queued. |
| 2 | Finishes | r1 finishes on s1 and r2 finishes on s2. |
| 2 | Scheduling | r3: s1 gives 2 ticks, s2 gives 3, so **s1** (finishes at t=4). r4: s2 gives 1 tick, so **s2** (finishes at t=3). |
| 3 | Finishes | r4 finishes on s2. |
| 4 | Finishes | r3 finishes on s1. |

This is the same set of events as the provided `run.jsonl`. Only the order of lines within a tick differs, and the validator sorts events before checking them.

## 12. Assumptions and trade-offs

- **Tick length:** `tick_seconds = 1` is required, so "per second" and "per tick" are the same thing.
- **No preemption or migration:** a started request stays on its server until it finishes.
- **Placement only looks at the present:** earliest finish considers only servers that can accept the request now, and never waits for a better server to free up. This is simpler and greedy, and may not be optimal for the cluster as a whole.
- **Skip-ahead vs. fairness:** skip-ahead keeps servers busier (more throughput) at the cost of strict fairness. `max_wait_ticks` sets the limit.
- **Leftover CPU is wasted in `shared` mode:** this follows the spec's wording, at a small cost in efficiency.
- **Server id order:** ids are compared as plain strings, not "naturally" (`s10` sorts before `s2`). This is documented rather than "fixed", because any fixed order is deterministic.
