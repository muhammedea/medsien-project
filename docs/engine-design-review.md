# Engine design review

## 1. Verify that every request finishes or is dropped

The supplied validator accepted a trace containing only the four sample arrival events. It reported zero finished and zero dropped. A bug that loses a queued request could therefore pass the validator test in section 10.

For every generated test case, check the events for each input request in emitted order. The sequence must be exactly one of the following:

- `REQUEST_ARRIVED → REQUEST_STARTED → REQUEST_FINISHED`
- `REQUEST_ARRIVED → REQUEST_DROPPED`

## 2. Define input validation at the boundaries

Section 8 leaves header-only request files and whitespace in request IDs unspecified. The supplied validator rejects an empty request file and strips surrounding whitespace from CSV request IDs.

Reject header-only files and IDs that are blank after trimming. Trim request IDs before checking uniqueness and use the trimmed ID in the trace. Require `max_wait_ticks` and `max_queue_length` to be nonnegative integers when supplied. Preserve zero as a valid value for both.

## 3. Compute the shared CPU allocation once per tick

In `advance()`, take the set of requests that ran during the elapsed tick and calculate each request’s share using that set’s size. Apply the share to every request before removing any completions. Otherwise, removing a short request during iteration could give a later request extra CPU in the same tick.

Test this with two requests of 1 and 6 work units starting together at `t=0` on a server with 10 CPU units per tick. Each receives a share of 5 during the first tick. The shorter request finishes at `t=1` and the longer at `t=2`. Swap their IDs and verify that the finish time for each workload stays the same.
