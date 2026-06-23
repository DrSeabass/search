# Algorithm Implementation Sequence

Port/build order for the parameterless Triangle Search work (AAAI). The goal
is a head-to-head evaluation of Triangle Search and its parameterless variants
against the recognized satisficing and anytime baskets, on this suite's classic
heuristic-search domains.

Status legend: **[have]** already in `search/` · **[port]** exists in the
Fast Downward / Scorpion tree, translate to this suite's `SearchAlgorithm<D>`
template idiom · **[build]** no implementation on hand.

Cross-repo coordination + deadlines: [`../AAAI_TRIANGLE_PAPER.md`](../AAAI_TRIANGLE_PAPER.md).

## Near-term execution plan (start here — Triangle + Rectangle first)

Goal: get the first cross-suite **batches running before ICAPS travel**. Port the two
base engines, smoke them, launch a baseline batch — then layer the parameterless
variants on top. Adaptive/ratchet are deltas on the Triangle engine, so the engine port
(step A) is the load-bearing step; everything else is mechanical or reuse.

**Burns idiom (confirmed from `beam.hpp` / `main.hpp`):**
- Algorithms are header-only: `template <class D> struct XSearch : public SearchAlgorithm<D>`
  in `search/X.hpp`. Define a `Node` with `closedentry/key/setind/getind/pred/prio/tieprio`,
  parse params from `argc/argv` in the ctor (e.g. `-width`, `-slope`), implement
  `search(D &d, State &s0)`. Reuse `Pool<Node>`, `closed`, and the open-list helpers
  `beam.hpp` uses. No PDDL/preferred-operator machinery — the Triangle mechanism is
  purely search-internal (per-depth open lists keyed h-then-g + an h-trend signal).
- Register the name in `search/main.hpp`: add `#include "X.hpp"` and an
  `else if (strcmp(argv[1], "x") == 0) return new XSearch<D>(argc, argv);` branch in
  `getsearch<D>()`. Domains pick it up for free (each `<domain>/main.cc` includes `main.hpp`).
- Invocation is stdin-fed: `cat inst | ./<domain>_solver triangle -slope 48`.

**Progress:**
- **[done 2026-06-22] A + B — Triangle and Rectangle ported, wired, built warning-clean
  (`-Werror`), and validated crash-free across ALL 8 working domains** (gridnav, vacuum,
  drobot, traffic, blocksworld, tiles, pancake, synth_tree) via the Lab study in
  `experiments/2026-06-aaai-triangle/`. `search/triangle.hpp`, `search/rectangle.hpp`;
  dispatch names `triangle` / `rectangle` in `search/main.hpp`.
  - **Two bugs found and fixed during bring-up:**
    1. *Anytime convergence:* originally only recorded the incumbent when the goal was
       reached as a *new* node, so re-reaching it more cheaply never improved the bound
       (Triangle stuck at a suboptimal cost). Fixed to check the goal for **every**
       retained successor (new / reopened / re-seen open), matching Scorpion. Anytime
       Triangle now converges to optimal (verified on blocksworld 9→6, pancake 54→49).
    2. *In-place-edge path corruption (pancake, synth_tree):* those domains define
       `PackedState == State`, `unpack()` returns a reference to the node's own stored
       state, and `Edge` applies the operator **in place** (undone on destruction). So
       calling `solpath()` while the `Edge` was live read mutated ancestor states and
       tripped `pathcost`'s assertion. Fixed by deferring `solpath`/incumbent handling
       until after `considerkid` returns (Edge destructed). `beam` sidesteps this by
       only detecting goals on pop. **Rule for any new algorithm here: never trace the
       path while an `Edge` is in scope.**
  - **[fixed 2026-06-22] Pre-existing suite bug:** `beam` crashed on `drobot`
    ("Updating an invalid heap index"). Root cause: `clear()` emptied the open list
    without resetting each element's tracked index, so a node discarded by beam kept a
    stale `openind >= 0`; a later duplicate then made `mem()` lie and `update()` ran on a
    stale index. Fixed `BinHeap::clear()` (`structs/binheap.hpp`) and the bucketed
    `OpenList<…,IntOpenCost>::clear()` (`search/search.hpp`) to reset indices on clear —
    a suite-wide hardening for any algorithm that clears an open list. `beam` now solves
    all 8 domains; full batch has 0 crash-errors. (Latent sibling: `minmaxheap.hpp`
    `clear()` has the same pattern; fix if a min-max-heap algorithm trips it.)
  - **[fixed 2026-06-22] Pre-existing suite bug:** `arastar` expanded 0 nodes on
    `blocksworld` (and any **unsigned-`Cost`** domain). Root cause: the "no incumbent
    yet" sentinel was `cost == Cost(-1)`, but for `unsigned int` Cost (blocksworld)
    `Cost(-1)` wraps to UINT_MAX and never equals the `double cost = -1.0` member, so
    `goodnodes()` returned false and the search stalled. Fixed both sentinel sites in
    `search/arastar.hpp` to test `cost < 0` / assign `cost = -1` (robust for signed,
    unsigned, and float Cost). ARA\* now solves blocksworld (cost 6 = optimal) and
    expands normally on all domains.
  - **Known limitation (pre-existing, applies to all anytime algos):** on OOM,
    `main.hpp` clears `res.path`, so an anytime run that exhausts memory mid-convergence
    (e.g. ARA\*/anytime-Triangle on a hard tiles instance) reports `final sol cost = -1`
    / coverage 0 — but its `#altrow "incumbent"` trajectory is preserved (that is the
    data the anytime score uses). Give anytime runs generous memory; on Tetralith each
    run has a dedicated core/memory so local 4-way contention doesn't apply.
  Original quick checks retained below:
  - tiles seed-42 4×4: A\* optimal = 53. `triangle` (slope 1) = 63 @ 3029 exp;
    `rectangle -width 100 -aspect 1` = 53 @ 602k exp; `-width 10 -aspect 5` = 55 @ 25k;
    `-width 3 -aspect 3` = 57 @ 11k. Clean width→quality/speed tradeoff.
  - `triangle -anytime` emits the `#altcols/#altrow "incumbent"` profile table the RDB
    parser reads, converges to optimal on a small grid, and terminates gracefully.
  - **Operational gotcha:** anytime `triangle` retains all closed nodes; on big
    instances it grows unbounded. `main.hpp`'s `bad_alloc` handler *clears* `res.path`,
    so "final sol cost" reports −1 on OOM — but the `#altrow` incumbents already printed
    survive (that's the anytime data). **Always pass `-mem <cap>` and `-walltime <s>`**
    to every Burns run; an unbounded anytime run will swap the box. Rectangle is
    width-bounded and does not have this growth.
  - Defaults: `triangle` slope=1, reopen on, anytime off
    (`-slope N`, `-anytime`, `-noreopen`); `rectangle` width=100, aspect=1, reopen on,
    anytime off (`-width N`, `-aspect N`, `-anytime`, `-noreopen`).
  - **[2026-06-23] Both converge to optimal.** `rectangle` now mirrors `triangle`:
    reopens closed nodes reached by a cheaper path (default on) and, with `-anytime`,
    keeps improving the incumbent under g-bound pruning until it exhausts the
    sub-incumbent space — so anytime cost converges to the optimum (verified on the
    non-unit drobot/gridnav domains; guarded by the `-anytime` regression rows). This
    diverges from the *current* Scorpion rectangle port, which is still first-solution
    / no-reopen — see cross-suite note below.
  - **[done 2026-06-23] Regression coverage:** `triangle`/`rectangle` (first-solution)
    added to the `regression/` matrix across domains (rectangle omitted on pancake — too
    slow), plus `beam` on drobot and `arastar` on blocksworld to lock in the two bug
    fixes. `golden.json` re-blessed (36 runs, ~13s, deterministic; `make regression`
    passes). Anytime mode is deliberately excluded from regression (unbounded/slow).
  - **[done 2026-06-23] Sequence items 3–5: the parameterless variants.** Extracted the
    shared engine into `triangle_engine.hpp` (`TriangleEngine<D>` base + virtual
    `cascade()`); `triangle` is now a thin subclass (behavior unchanged — regression
    matches). Added `adaptive_triangle` (budget-driven dive depth; `-penalty N`,
    default 1, 0 = parameterless) and `ratchet_triangle` (slope doubles/halves by
    per-step h-trend; `-slope` initial). Both carry the Direction-B `-liftfloor` knob
    (adaptive also `-floorproxy informedness|layers_added`). Both converge to the
    optimum with `-anytime` (verified: drobot 5.884319, tiles 53). Added to the
    correctness regression (56 runs; drobot `-anytime` rows for all four pinned at the
    optimum) and the perf suite (10 probes). multi_triangle / lazy_triangle remain ICAPS
    scope (below).

**Steps:**

- **A. Port Triangle (static slope) → `search/triangle.hpp`.** Translate
  `triangle_search.cc` from Scorpion. Map FD's `EvaluationContext`/per-layer open lists
  onto a vector of Burns open lists keyed (h, then g); reproduce the cascade /
  layer-extension logic (`609cffb2a`/`a2444a2d7` in Scorpion: extend the deque lazily,
  drain ineligible entries, break the cascade on a missing layer). Param: `-slope`.
  Wire dispatch name `triangle`.
- **B. Port Rectangle → `search/rectangle.hpp`.** The ablation (Triangle minus
  per-iteration deepening); easier given A. Confirm the two int option names
  (width/aspect) and expose as `-width` / `-aspect`. Wire dispatch name `rectangle`.
- **C. Smoke-test.** Build the domain solvers (`make`), run both on a few
  tiles / pancake / blocksworld instances; sanity-check solution cost vs `astar`/`greedy`
  and confirm anytime output (`#altcols "incumbent"`). Add a golden-number row to
  `regression/` per the README's smoke-test convention.
- **D. First Lab batch.** Reuse `experiments/searchlab/` (Lab `Experiment`+`Run`, the
  `run-solver.sh` stdin shim, the RDB parser). Configs: `triangle` (slope sweep
  {1,2,4,8,16,32,48,64}), `rectangle`, plus existing baselines `greedy`, `wastar`,
  `beam`, `arastar`. Same time/memory limits as the FD side. Launch on Tetralith — this
  is the batch to get running before travel. The slope sweep doubles as the **headline
  figure** check (does best static slope vary by domain?).
- **E. Layer the variants.** Once A–D are green, add `adaptive_triangle` and
  `ratchet_triangle` as deltas on the Triangle engine (steps 3–4 below), plus the
  `lift_floor` flag (step 5), and re-launch the batch with the parameterless configs
  and ANA\* once it exists here.

## Sequence

### 1. Triangle engine + variants (the contribution)

Build the depth-striated open-list engine once (item 1); the rest are deltas on
it. Mechanism is purely search-internal (per-depth open lists keyed h-then-g, an
h-trend signal) — no preferred operators or other planning-specific signals.

1. **Triangle Search (static slope)** — anytime / depth-striated beam — **[port]**
   - The engine. `src/search/search_algorithms/triangle_search.cc` in Scorpion.
   - Lemons, Ruml, Linares López, Holte. *Triangle Search: An Anytime Beam
     Search.* ICAPS 2023 HSDIP Workshop. (Extended version: arXiv:2312.12554.)

2. **Rectangle Search** — anytime beam — **[port]**
   - The ablation (Triangle minus per-iteration deepening) and the parent
     algorithm. `rectangle_search.cc` in Scorpion.
   - Lemons, Ruml, Holte, Linares López. *Rectangle Search: An Anytime Beam
     Search.* AAAI 2024.

3. **Adaptive Triangle (parameterless, primary)** — anytime / adaptive beam — **[port]**
   - Triangle engine + informedness counter driving cascade depth; removes the
     slope parameter. `adaptive_triangle_search.cc` in Scorpion. This work.

4. **Ratchet Triangle (parameterless, corroboration)** — anytime / adaptive beam — **[port]**
   - Triangle engine + persistent doubling/halving slope; second independent
     parameterless rule. `ratchet_triangle_search.cc` in Scorpion. This work.

5. **Floor-lifting paths (`lift_floor`, `non_progress_penalty`)** — variant knobs — **[port]**
   - Relaxed cascade start-depth ("bring up the rear"). Underperforms in
     planning; ported here to test whether that failure is planning-specific or
     general. Off by default => bit-identical to items 3/4. This work.

### 2. Baselines to add (expected comparisons)

6. **ANA\*** — anytime, nonparametric — **[done]** (`search/ana.hpp`, name `ana`)
   - The existing *parameterless* anytime search; the direct foil to the
     parameterless Triangle claim. Highest-priority baseline.
   - van den Berg, Shah, Huang, Goldberg. *Anytime Nonparametric A\*.* AAAI 2011.
   - Ported from Scorpion's `anytime_nonparametric_search`. Single potential-
     ordered heap, re-keyed on each incumbent improvement (`reorderopen()`).
     Defaults `reopen=true`, first-solution mode; `-anytime` converges to
     optimal (verified on drobot/gridnav, reaches A*'s optimum). Cross-multiplied
     potential done in double, since gridnav's Cost class has no operator*.

7. **ε-GBFS** — satisficing, exploratory GBFS — **[build]**
   - ε-greedy node selection on top of GBFS. Cheap; defuses "compared only to
     vanilla GBFS." General-purpose (no per-domain type function needed).
   - Valenzano, Sturtevant, Schaeffer, Xie. *A Comparison of Knowledge-Based
     GBFS Enhancements and Knowledge-Free Exploration.* ICAPS 2014.

8. **Anytime / Restarting Weighted A\*** — anytime wA\* — **[build]**
   - The expected anytime-wA\* baseline; RWA\* also bridges to LAMA's spine.
     (Note: `restartingsearch.hpp` is a real-time execute-and-replan loop, not
     this.) Build one of:
   - AWA\*: Hansen, Zhou. *Anytime Heuristic Search.* JAIR 2007.
   - RWA\*: Richter, Thayer, Ruml. *The Joy of Forgetting: Faster Anytime Search
     via Restarting.* ICAPS 2010.

9. **Type-based exploration / DBFS** — satisficing, exploratory GBFS — **[build]**
   - Most-cited exploratory-GBFS line, but needs a per-domain type function and
     was evaluated in planning. Lower priority: build for the planning suite, or
     cite-and-defer for the classic-search suite.
   - Xie, Müller, Holte, Marinescu. *Type-Based Exploration with Multiple Search
     Queues for Satisficing Planning.* AAAI 2014.
   - Imai, Kishimoto. *A Novel Technique for Avoiding Plateaus of Greedy
     Best-First Search in Satisficing Planning* (DBFS). AAAI 2011.

## Reverse direction: baselines into Scorpion / FD

The AAAI evaluation runs Triangle on both suites, so a baseline only helps in
the suite where it exists. The contribution flows FD -> here; classic-search
baselines flow here -> FD. Status below is relative to the **FD/Scorpion** tree.

- **ε-GBFS** — *already in FD, no port.* Wire the `epsilon_greedy` open list into
  an eager-greedy config (`src/search/open_lists/epsilon_greedy_open_list.*`).
- **Type-based exploration** — *already in FD, no port.* `type_based` open list
  (`src/search/open_lists/type_based_open_list.*`); covers item 9 on the
  planning suite for free.
- **ANA\*** — **[build in FD]**, no analog there. The parameterless anytime foil
  must exist in both suites for the parameterless-vs-parameterless comparison to
  hold on the planning suite too. van den Berg, Shah, Huang, Goldberg. *Anytime
  Nonparametric A\*.* AAAI 2011.
- **Anytime EES (AEES)** — **[build in FD]**, hard, optional. EES exists in this
  suite (`ees.hpp`) but not in FD, and FD doesn't natively expose the
  distance-to-go (*d*) or debiased (*ĥ*, *d̂*) estimates EES needs — so a planning
  port means standing up that estimate infrastructure first, not just the
  algorithm. Treat as stretch / classic-suite-only. Base algorithm: Thayer,
  Ruml. *Bounded Suboptimal Search: A Direct Approach Using Inadmissible
  Estimates.* IJCAI 2011. (Drop in the exact AEES reference.)

## Already present — reuse as baselines, no work

- **GBFS** (`greedy.hpp`; supports speedy/d-based key and optional dup-dropping)
- **Weighted A\*** (`wastar.hpp`)
- **Beam search** (`beam.hpp`) — the width-restricted relative Triangle is pitched against
- **ARA\*** (`arastar.hpp`) — standard anytime baseline
- **BUGSY** (`bugsy.hpp`) — utility-guided anytime; optional
- **EES** (`ees.hpp`) — bounded-suboptimal; cite, not a direct anytime competitor
- A\*, UCS, IDA\* — available if needed

## Experiment harness (tooling)

Use **Downward Lab** (the same framework the Scorpion/FD experiments use), so
both suites share one analysis pipeline and the cross-suite tables come out of
the same machinery. Set aside the MongoDB document-store design in
`experiment_running_description.md` / `agentic_experiment_running_plan.md` — it's
a more ambitious general-purpose effort, orthogonal to getting the paper out.

Build (mostly reuse, not new code):

- **Generic Lab layer, not the `downward` package.** `lab.experiment.Experiment`
  + `Run`, not `FastDownwardExperiment` — Burns has no translate/preprocess/PDDL
  pipeline for the `downward` specialization to drive.
- **Reuse `project.py`** nearly verbatim from a recent Scorpion experiment dir
  (e.g. `experiments/2026-05-triangle-vs-lama/`): its Tetralith/Slurm
  `Environment` subclass and report helpers are framework-agnostic.
- **`run-solver.sh` shim** added as a Lab resource: Burns reads the instance from
  stdin (`cat inst | ./solver alg args`), which Lab's no-shell `add_command`
  doesn't do directly.
- **RDB parser** mapping solver output to Lab attributes; reuse the parsing logic
  already in `utils/rdb_to_json.py`. Scalars from `#pair` (wall time, expansions,
  solution cost, derived `solved`); the anytime `#altcols "incumbent"` table
  gives the (time, cost) series for anytime profiles → store in run properties
  for a custom report.
- **Lab owns time/memory limits**, same values as the FD side, for a fair
  cross-suite comparison.
- **Instances**: enumerate the `key_file` directory hierarchy each domain's
  `make_instances.py` produces (walk code already in
  `agentic_experiment_running_plan.md` §1) into Lab Runs.

## Out of scope here (ICAPS / planning-enhancement paper)

- **Multi-heuristic Triangle** (`multi_triangle_search.*` in Scorpion)
- **Lazy Triangle** (`lazy_triangle_search.*` in Scorpion; the LAZY-TRI puzzle)
