# Development Log

A dated record of how this project was built: what I worked on, how I used AI.

## How AI was used

- **Tools:** Claude Code (Claude Opus 5.5). Codex (for review)
- **Usage:** Analyzing the requirements, writing design document, implemnting and generating tests.

---

## 2026-11-25: Reading the assignment and init

- I have started reading the PDF and quick looking the files.
- Created the project with assingment files, devlog and readme.
- I decided to use FastAPI for now.

## 2026-11-25: Investigating the requirements

- I have used Claude Code to analyze requirements. 
**Prompt:**
> This is a take home project that I've got. Please review project-info files and explain it to me. Read the validate_run.py

**AI output summary:**
- Summarized the requirements: a deterministic tick engine, FastAPI, a server CRUD dashboard, Docker Compose, and a suggested design.
- Pointed out that **spec Section 4 contradicts `validate_run.py`**. The spec allows several requests per server at once, sharing the CPU. The validator rejects overlapping runs on a server.

**Prompt:**
> What I don't understand is that. What the servers should be. What I mean, should I just write a server and it will have multiple instances. And one load-balancer that does real http requests to these servers. Doing this way will make the determinism very hard.

**AI output summary:**
No. You don't run any real servers, and there's no real HTTP traffic between a load balancer and workers. Everything is a simulation.

**Prompt:**
> about the spec and the validator missmatch, maybe the example requests.csv and servers.json does not create possible overlap so they wrote this validator specificly for this example

**AI output summary:**
No. The example data does allow overlap. The validator isn't written around this data. This is an open question.

**Verification:**
- Ran the validator on the provided `run.jsonl`: it is **VALID**.
- Had the AI write a trace that follows the Section 4 CPU-sharing model, then ran the validator on it: it is **INVALID**, with finish-time mismatches and an "overlapping runs" error on `s1`. This confirms the contradiction is real.
- Read the validator source myself to check the line references.

**Decision:** Decided to email Medsien before choosing an execution model.

- I have emailed Medsien with these questions:
> 1. Execution model vs. validate_run.py
> Section 4 of the spec says a server may run multiple requests at the same time, with cpu_units_per_tick split evenly among them and memory added up. The provided validate_run.py assumes one request per server at a time. It rejects any overlapping runs on the same server and assumes the request gets the full CPU. Also it checks memory per request rather than the total across running requests.
> I can make two modes, single request per server and concurrent mode. Default mode will pass the validator.
> 
> 2. Scope of the "servers"
> My understanding is that the servers and requests are fully simulated. Servers are configuration records, and execution is modeled tick by tick in a deterministic engine, with no real worker processes and no real HTTP traffic between a load balancer and backends. The only real HTTP would be between the dashboard and the backend API, for managing servers, starting runs... Is that correct?

**Prompt:**
> Is there any other open quesitons. Also when I look at the run.jsonl, these are my assumptions:
> - On the start of the tick. Request arrive events should be logged and processed but not started
> - Then if there is any finished requests log their finish and process
> - Evaluate arrived requests 
>   - Log drop events for rejected ones
>   - logs start events

**AI output summary:**
Mostly correct, for the fisrt step Schedule the queue, not just new arrivals. Also Advance CPU work before logging finishes. This current algorithm:
```
1. log REQUEST_ARRIVED for requests with arrival == t, append to queue
2. apply CPU from tick t-1 → log REQUEST_FINISHED (sorted by server_id, request_id), free memory
3. go through the queue in FIFO order:
     can never fit (mem > every server)    → REQUEST_DROPPED
     fits a server (strategy + tie-break)  → REQUEST_STARTED
     otherwise wait; drop if over queue length / max-wait policy
```

## 2026-11-25: Clarification email and Design Document

- I have got the aswers from the Medsien team
> 1. Execution model: Your plan works. Make single request per server the default so validate_run.py passes. Concurrent mode as described in Section 4 is a welcome extra but not required. If you build it, please explain the difference between the two modes briefly in your README.
> 2. Scope of the servers: Yes, that's correct. Servers and requests are fully simulated: servers are configuration records and execution runs tick by tick in a deterministic engine. There are no real worker processes and no real HTTP traffic between the load balancer and the servers. 

**Prompt:**
> Ok I have got the answer from Medsien team:
>
> ... Answers in the email ...
> 
> I want to have swappable execution model. Your previous plan was good. Lets start with the engine plus CLI. Project structure will be like a backend folder and frontend folder at the top level. Backend Python FastAPI, frontend Vite React. Create the initial design at docs/engine-design.md
> Please ask me anything that needs to be decided. But optional features can be implemented later skip them.

**AI output summary:**
- First these questions aswered like this:
   - Queue order: first in, first out, but later requests can skip ahead of one that can't be placed (§5.1).
  - Server choice: the server where the request would finish soonest, with ties going to the lowest server id (§5.2).
  - Overload: a request too big for every server is dropped at arrival. The maximum wait and maximum queue length are both off by default (§6).
  - Shared-mode CPU: each request gets an exact equal share, and CPU a request doesn't need in its last tick is wasted (§3.2).
- Dropped requests get a reason field.
- Design document created.

## 2026-11-25: Review Design Document
- I used Codex for reviewing the design document

**Prompt (codex):**
> This is a take home project that I've got. 
> First read the project-info folder then look at the engine-design. Do you see any problem? Would you recommend anything?

**AI output summary:**
It find 3 issues. I asked it to make it a review document. 

**Prompt (CC):**
> Another agent has done a review for your design in docs/engine-design-review.md Look into it and ıs there anything worth changeing. Defend your design.

**AI output summary:**
I accepted all three points and updated. None of them changes a design decision: two make the doc more precise and one closes a real gap in the tests

- I have examined the design manually, specificly Section 4 (The tick loop).

## 2026-11-25: High-level Design

**Prompt (Codex):**
> I want you to give me advice on project structure.
> My Notes: There is 2 sub project backend and frontend. A Docker compose file at the top. Backend will be Python FastAPI. Frontend should be vite, react, typescript project.
> Also comment on should I use a database.

**AI output summary:**
Folder structure and key points. It has recommended sqlite as database is enough. 

**Prompt (Codex):**
> Where should I store run results? In database or a folder that is mounted.

**AI output summary:**
I’d store each run in a folder on a mounted volume and use SQLite for the editable server configuration. The assignment requires a downloadable run.jsonl

**Prompt (Codex):**
> Ok this is good. Also sqlite should have runs table in it. I want you to make this a very concise design document as high level design. 

**AI output summary:**
It has created docs/high-level-design-codex.md file. (I renamed)

**Prompt (CC):**
> I want you to create a high level design. about project structure. Make it concise. Use docs/high-level-design-codex.md as entry point and improve on it. Also create a concise AGENTS.md file. Also update readme.

**AI output summary:**

It has created docs/high-level-design.md file. Created AGENTS.md and README. It has made runid the hash of the inputs. For re-runs It suggests ENGINE_VERSION. 

**Prompt (CC):**
> Maybe we should not make runid a hash. Just use the timestamp as id or a monotonically increasing int. Do we need run cache?
> This will not affect the assignment requirements, right? If not just do the changes.

**AI output summary:**
Run ids are now auto-increment integers and there's no result cache.

**Prompt (CC):**
> Design says "runs with the same `input_hash` must have the same `trace_hash`." Is this a different thing?

**AI output summary:**
There was a mistake. It has done some documentation changes.

## 2026-11-26: High Level Implementation

- I have deleted unnecessary docs.
- I have prepared a promp for implementing high level structure and the engine. 

**Prompt (CC):**
> I want you to implement the high level project structure and the engine. 
> Use docs/high-level-design.md and docs/engine-design.md for implementation details. 
> 
> My Notes:
> - Implement engine in backend. It can be used as a CLI.
> - For development I should be able tu run without docker
> - I have uv. You can use it for python environment. 
> - Add Dockerfiles also
> - Don't implement frontend for now. Just add necessary files and structure. 
> 
> You can ask me anything if anything is not clear?

**AI output summary:**

The engine and CLI are built and tested, and the project structure is in place. The Docker images haven't been built yet.

**Prompt (Codex):**
> Another agent implemented the engine. I want you to read docs/high-level-design.md and docs/engine-design.md again and look into the implementation. Tell me your opinion. Do you see any major problem? Do you have any suggestions?

**AI output summary:**
The engine is ready for API integration after one submission blocker is fixed. Review is stored in docs/engine-implementation-review.md

**Prompt (CC):**
> I have committed everything.
> Another agent has done a review on this implementation. It is in: docs/engine-implementation-review.md
> Look into it and is there anything worth changing? Defend your implementation.

**AI output summary:**

I accepted all four findings, but I fixed two of them differently from what the review suggested. 1,296 tests now pass, including on a copy of the repo that contains only the files Git will commit.
1. Test fixture never committed (high): accepted, my mistake.
2. Slow runs (medium): accepted, and it was worse than the review measured.
3. README command can't be pasted into a shell (low): accepted.
4. Order of queue-full drop events (low): I kept the code and fixed the doc.

## 2026-11-26: UI and API Implementation

**Prompt (CC):**
> I want you to create a UI requirements document. What I understand, we will have 2 main menu item. Servers and Runs. For runs user can upload csv. Also recommend a simultaion visualization UI in run details. Sample csv should be default one. Because requirement says reviewer should run sample tast easily

**AI output summary:**
docs/ui-requirements.md file is created

**Prompt (CC new session):**
> This is a Project for a Deterministic Load Balancer Simulation.
> Navigate the repo and understand. Read all the documents in the docs folder.
> 
> I want you to implement frontend and the necessary API endpoints in backend according to the document in docs/ui-requirements.md
> You can use a component library like shadcn-ui.
> You can ask me if anything is unclear.

**AI output summary:**
The backend API and the full dashboard from docs/ui-requirements.md are built. Including the simulation visualitation.

- UI implementation is tested manually by using Docker.
