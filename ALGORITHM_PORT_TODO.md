# Algorithm Implementation Sequence

Port/build order for the parameterless Triangle Search work (AAAI). The goal
is a head-to-head evaluation of Triangle Search and its parameterless variants
against the recognized satisficing and anytime baskets, on this suite's classic
heuristic-search domains.

Status legend: **[have]** already in `search/` · **[port]** exists in the
Fast Downward / Scorpion tree, translate to this suite's `SearchAlgorithm<D>`
template idiom · **[build]** no implementation on hand.

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

6. **ANA\*** — anytime, nonparametric — **[build]**
   - The existing *parameterless* anytime search; the direct foil to the
     parameterless Triangle claim. Highest-priority baseline.
   - van den Berg, Shah, Huang, Goldberg. *Anytime Nonparametric A\*.* AAAI 2011.

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
