// Copyright © 2026 the Search Authors under the MIT license. See AUTHORS for the list of authors.
//
// Adaptive Rectangle Search: a fork of rectangle (Lemons, Ruml, Holte,
// Sturtevant, AAAI 2024) whose single parameter -- the aspect ratio a -- is set
// ONLINE and parameter-free instead of fixed. There is no beam width and no
// static aspect knob; the rectangle "rotates" as a changes.
//
// The traversal is identical to the faithful base (rectangle.hpp): the frontier
// is bucketed by search depth `de` into `rect`, ordered within a depth by h, and
// the rectangle grows with the `iteration` counter (each depth level admits
// iteration * delta_across expansions; the rectangle reaches depth
// iteration * delta_down). The only difference is that (delta_down, delta_across)
// are recomputed from a live aspect a -- (a, 1) if a >= 1 else (1, 1/a) -- rather
// than a constant.
//
// a is driven by a parameter-free two-way ratchet in the same multiplicative
// spirit as ratchet_triangle.hpp (which doubles/halves its slope each step): the
// aspect doubles (rotate deeper) or halves (rotate wider) at each sweep boundary
// based on a majority vote, and is always a power of two, clamped to
// [2^-10, 2^10] as a safety rail (NOT a tuning knob).
//
// THE SIGNAL is STRUCTURAL -- a best-first-chain signal, not a heuristic
// gradient. Within a sweep, the FIRST (best-h) node expanded at each depth level
// is the head of that level's beam. When a head is expanded, it votes on one
// question: is the node now at the FRONT (best-h) of the next depth's bucket one
// of the successors this head just produced? If yes, the greedy best-first chain
// stayed intact from one depth to the next (a deep-narrow rectangle is tracking a
// real gradient toward the goal -> vote to deepen). If no, the best path is
// scattering across the frontier (a wider sweep is better -> vote to widen).
// Only the head of each level's beam votes; skipped/pruned nodes do not. Over a
// completed sweep these per-level votes are tallied and the ratchet fires at the
// boundary:
//   chain-intact votes strictly dominate -> a *= 2  (rotate deeper)
//   chain-broken votes strictly dominate -> a /= 2  (rotate wider)
//   tie / no data                        -> hold
//
// An earlier, WRONG signal (a per-edge h-gradient: "informed iff child h <
// parent h") was tried and fails here: the rectangle sweeps breadth-first, not
// as a dive, so parent-child h comparisons mostly read "uninformed", the aspect
// collapses monotonically to the wide floor, the search goes near-breadth-first,
// and coverage craters on large instances. The best-first-chain signal fixes
// this: the aspect dives deep early and oscillates in a healthy range instead of
// pinning at a rail. Completeness/optimality do not depend on a -- iteration
// grows without bound and every depth level keeps being served, so the dynamic
// aspect changes only the expansion order.
//
// adaptive_triangle / ratchet_triangle are the width-1 relatives of this search.
//
// Ported from src/search/search_algorithms/adaptive_rectangle_search.{h,cc}
// (Scorpion).
#pragma once
#include "../search/search.hpp"
#include "../utils/pool.hpp"
#include <algorithm>
#include <cstring>
#include <cstdlib>
#include <set>
#include <utility>
#include <vector>

void dfrowhdr(FILE *, const char *, unsigned int ncols, ...);
void dfrow(FILE *, const char *, const char *, ...);
void fatal(const char *, ...);

template <class D> struct AdaptiveRectangleSearch : public SearchAlgorithm<D> {

	typedef typename D::State State;
	typedef typename D::PackedState PackedState;
	typedef typename D::Cost Cost;
	typedef typename D::Oper Oper;

	struct Node {
		PackedState state;
		Node *parent;
		Oper op, pop;
		Cost g, h;
		unsigned long seq;	// stable per-state id; keys the depth buckets
		int de;			// search depth (which `rect` bucket the node lives in)
		bool expanded;		// true == closed (removed from rect)

		Node() : parent(NULL), seq(0), de(0), expanded(false) {
		}

		static ClosedEntry<Node, D> &closedentry(Node *n) {
			return n->closedent;
		}

		static PackedState &key(Node *n) {
			return n->state;
		}

	private:
		ClosedEntry<Node, D> closedent;
	};

	// A frontier entry is (h value, unique per-state sequence number). The h
	// value orders each depth bucket (best-h first); seq breaks ties (earliest
	// inserted first) and gives each state a stable key so it can be erased when
	// its g improves and it moves to a new depth.
	typedef std::pair<Cost, unsigned long> Entry;

	// Safety rails on the live aspect (not tuning knobs): keep a in a range where
	// iteration * delta stays well behaved and the schedule never degenerates to
	// a single shape forever.
	static constexpr double ASPECT_FLOOR = 1.0 / 1024.0;
	static constexpr double ASPECT_CEILING = 1024.0;

	AdaptiveRectangleSearch(int argc, const char *argv[]) :
		SearchAlgorithm<D>(argc, argv), closed(30000001) {
		anytime = false;
		reopen = true;
		for (int i = 0; i < argc; i++) {
			if (strcmp(argv[i], "-anytime") == 0)
				anytime = true;
			else if (strcmp(argv[i], "-noreopen") == 0)
				reopen = false;
		}
		// No -aspect / -width: the aspect is set online and parameter-free.
		nodes = new Pool<Node>();
	}

	~AdaptiveRectangleSearch() {
		delete nodes;
	}

	void search(D &d, typename D::State &s0) {
		rowhdr();
		this->start();
		closed.init(d);

		aspect = 1.0;
		recomputedeltas();
		iteration = 1;
		level = 0;
		chainintact = 0;
		chainbroken = 0;
		spinelevel = -1;

		Node *n0 = nodes->construct();
		d.pack(n0->state, s0);
		n0->g = Cost(0);
		n0->h = d.h(s0);
		n0->op = n0->pop = D::Nop;
		n0->parent = NULL;
		n0->expanded = false;
		n0->de = 0;
		assignseq(n0);
		closed.add(n0, n0->state.hash(&d));

		if (d.isgoal(s0)) {	// start == goal: cost 0 is trivially optimal
			updateincumbent(d, n0);
			this->finish();
			return;
		}

		ensurelevel(0);
		frontierinsert(n0);

		bool done = false;
		while (!done && !this->limit() && hasnonempty())
			done = step(d);

		// In anytime mode the loop ends either because a limit was hit or
		// because the rectangle was exhausted; the latter (with an incumbent in
		// hand) proves the incumbent optimal.
		converged = anytime && haveincumbent && !this->limit();

		this->finish();
	}

	virtual void reset() {
		SearchAlgorithm<D>::reset();
		rect.clear();
		ec.clear();
		seqtonode.clear();
		nextseq = 0;
		iteration = 1;
		level = 0;
		aspect = 1.0;
		chainintact = 0;
		chainbroken = 0;
		spinelevel = -1;
		haveincumbent = false;
		nincumbent = 0;
		converged = false;
		closed.clear();
		delete nodes;
		nodes = new Pool<Node>();
	}

	virtual void output(FILE *out) {
		SearchAlgorithm<D>::output(out);
		closed.prstats(stdout, "closed ");
		dfpair(stdout, "open list type", "%s", "vector of h-ordered depth sets");
		dfpair(stdout, "node size", "%u", sizeof(Node));
		dfpair(stdout, "aspect policy", "%s", "best-first-chain ratchet (power of 2)");
		dfpair(stdout, "final aspect", "%g", aspect);
		dfpair(stdout, "iterations", "%d", iteration);
		dfpair(stdout, "anytime", "%s", anytime ? "true" : "false");
		dfpair(stdout, "reopen closed", "%s", reopen ? "true" : "false");
		dfpair(stdout, "converged", "%s", converged ? "yes" : "no");
	}

private:

	void recomputedeltas() {
		// (delta_down, delta_across) = (a, 1) if a >= 1 else (1, 1/a).
		if (aspect >= 1.0) {
			delta_down = aspect;
			delta_across = 1.0;
		} else {
			delta_down = 1.0;
			delta_across = 1.0 / aspect;
		}
	}

	// Best-first-chain ratchet, applied at each completed rectangle sweep. Rotate
	// deeper (a *= 2) when chain-intact votes strictly dominate, wider (a /= 2)
	// when chain-broken votes strictly dominate, hold on a tie or no data. Then
	// reset the tallies and per-sweep spine tracker and recompute the split.
	void applyaspectratchet() {
		if (chainintact > chainbroken)
			aspect = std::min(aspect * 2.0, ASPECT_CEILING);
		else if (chainbroken > chainintact)
			aspect = std::max(aspect / 2.0, ASPECT_FLOOR);
		chainintact = 0;
		chainbroken = 0;
		spinelevel = -1;
		recomputedeltas();
	}

	// One expansion. Advance the rectangle to the next eligible node (skipping
	// any that can no longer improve the incumbent), expand it, and grow the
	// per-level expansion budget as the iteration counter advances. Returns true
	// iff the search should stop (first solution in non-anytime mode).
	bool step(D &d) {
		Node *n = NULL;
		while (!n) {
			if (!advancerectangle())
				return false;	// rectangle exhausted
			Entry e = *rect[level].begin();
			rect[level].erase(rect[level].begin());
			Node *cand = seqtonode[e.second];

			// Skip nodes that can no longer improve the incumbent (close without
			// expanding); skipped nodes do not vote.
			if (haveincumbent && cand->g + cand->h >= incumbent) {
				cand->expanded = true;
				continue;
			}
			n = cand;
		}

		// This node is the head of its level's beam iff it is the first node
		// expanded at this depth in the current sweep (levels are served in
		// increasing order). Only the head casts the best-first-chain vote.
		bool firstinbeam = level > spinelevel;
		if (firstinbeam)
			spinelevel = level;

		// Lazily create the next depth level just before it may be needed, then
		// count this expansion against the current level's budget.
		if ((double) level >= (iteration - 1) * delta_down)
			ensurelevel(level + 1);
		ec[level]++;

		return expand(d, n, firstinbeam);
	}

	// Advance `iteration`/`level` to the next rectangle cell eligible for
	// expansion, or report that none remain. The aspect ratchet fires at each
	// `iteration` boundary (a completed sweep).
	bool advancerectangle() {
		while (true) {
			if (level < (int) rect.size() && !rect[level].empty() &&
			    ec[level] < iteration * delta_across)
				return true;
			if (level < iteration * delta_down - 1)
				++level;
			else if (hasnonempty()) {
				applyaspectratchet();
				++iteration;
				level = 0;
			} else
				return false;
		}
	}

	// Close `n` (already removed from its depth bucket) and route its successors
	// into depth de+1. When `firstinbeam`, casts the best-first-chain vote for
	// the aspect ratchet. Returns true iff the search should stop (first-solution
	// goal in non-anytime mode).
	bool expand(D &d, Node *n, bool firstinbeam) {
		n->expanded = true;
		this->res.expd++;

		int de = n->de;
		ensurelevel(de + 1);

		// Successors this node places on the next depth bucket (de + 1); used for
		// the best-first-chain vote below.
		insertedkids.clear();

		bool stop = false;
		State buf, &state = d.unpack(buf, n->state);
		typename D::Operators ops(d, state);
		for (unsigned int k = 0; k < ops.size(); k++) {
			if (ops[k] == n->pop)
				continue;
			this->res.gend++;
			if (considerkid(d, n, state, ops[k], de + 1)) {
				// Edge is out of scope now; tracing the path is safe.
				updateincumbent(d, goalnode);
				if (!anytime) {
					stop = true;
					break;
				}
			}
		}

		// Best-first-chain vote (only for the head of this level's beam): did the
		// node just expanded produce the node now at the front of the next
		// depth's bucket? If so the greedy best-first chain is intact (deepen);
		// otherwise the best path is scattering across the frontier (widen).
		if (firstinbeam) {
			int next = de + 1;
			bool intact = false;
			if (next < (int) rect.size() && !rect[next].empty()) {
				unsigned long frontseq = rect[next].begin()->second;
				for (unsigned long kidseq : insertedkids) {
					if (kidseq == frontseq) {
						intact = true;
						break;
					}
				}
			}
			if (intact)
				chainintact++;
			else
				chainbroken++;
		}

		return stop;
	}

	// Generate one successor into depth `childde`. Returns true iff it is a goal
	// (the caller records the incumbent once the Edge is out of scope).
	bool considerkid(D &d, Node *parent, State &state, Oper op, int childde) {
		typename D::Edge e(d, state, op);
		Cost g = parent->g + e.cost;

		// g-only bound pruning: once we hold an incumbent, a successor whose g
		// already meets or exceeds it cannot improve on it. (g is monotone, so
		// this is safe and lets the anytime search converge to the optimum.)
		if (haveincumbent && g >= incumbent)
			return false;

		// Pack into a fresh node and look it up; destruct it if it is a
		// duplicate (some domains have non-copyable PackedState, so we cannot
		// pack into a temporary and copy -- mirror beam.hpp's idiom).
		Node *kid = nodes->construct();
		d.pack(kid->state, e.state);
		unsigned long hash = kid->state.hash(&d);
		Node *dup = static_cast<Node *>(closed.find(kid->state, hash));

		Node *target;
		if (!dup) {
			kid->g = g;
			kid->h = d.h(e.state);
			kid->parent = parent;
			kid->op = op;
			kid->pop = e.revop;
			kid->expanded = false;
			kid->de = childde;
			assignseq(kid);
			closed.add(kid, hash);
			target = kid;
		} else {
			this->res.dups++;
			nodes->destruct(kid);
			if (dup->expanded) {
				// Reopen a closed node reached by a strictly cheaper path so the
				// corrected g propagates to its successors. A closed node is not
				// in any bucket, so no erase is needed.
				if (!reopen || g >= dup->g)
					return false;
				dup->g = g;
				dup->parent = parent;
				dup->op = op;
				dup->pop = e.revop;
				dup->expanded = false;
				dup->de = childde;
				this->res.reopnd++;
				target = dup;
			} else if (g < dup->g) {
				// A strictly cheaper path to a still-open node. Remove it from
				// its current bucket (h is unchanged, only de/g move), re-parent,
				// and reinsert at the new depth below.
				frontiererase(dup);
				dup->g = g;
				dup->parent = parent;
				dup->op = op;
				dup->pop = e.revop;
				dup->de = childde;
				target = dup;
			} else {
				return false;	// duplicate without a lower g -- prune
			}
		}

		// Record the goal only; the caller traces the path once `e` is destructed
		// (some domains apply the operator in place and return a reference to the
		// node's own state -- see triangle.hpp). Goals are never inserted into a
		// bucket, and do not count toward the chain vote.
		if (d.isgoal(e.state)) {
			goalnode = target;
			return true;
		}

		frontierinsert(target);
		insertedkids.push_back(target->seq);
		return false;
	}

	void assignseq(Node *n) {
		n->seq = nextseq++;
		seqtonode.push_back(n);
	}

	void ensurelevel(int idx) {
		while ((int) rect.size() <= idx) {
			rect.push_back(std::set<Entry>());
			ec.push_back(0);
		}
	}

	// Insert a frontier node into its depth bucket, keyed on its h (the within-
	// depth ordering) and stable seq.
	void frontierinsert(Node *n) {
		ensurelevel(n->de);
		rect[n->de].insert(Entry(n->h, n->seq));
	}

	// Remove a frontier node from its depth bucket. Must be called with the
	// node's current de/h (before those change) so the stored key matches.
	void frontiererase(Node *n) {
		rect[n->de].erase(Entry(n->h, n->seq));
	}

	bool hasnonempty() const {
		for (const std::set<Entry> &bucket : rect) {
			if (!bucket.empty())
				return true;
		}
		return false;
	}

	void updateincumbent(D &d, Node *goal) {
		Cost c = goal->g;
		if (haveincumbent && !(c < incumbent))
			return;
		incumbent = c;
		haveincumbent = true;
		solpath<D, Node>(d, goal, this->res);
		nincumbent++;
		dfrow(stdout, "incumbent", "uuugg", nincumbent, this->res.expd,
			this->res.gend, (double) c, walltime() - this->res.wallstart);
	}

	void rowhdr() {
		dfrowhdr(stdout, "incumbent", 5, "num", "nodes expanded",
			"nodes generated", "solution cost", "wall time");
	}

	double aspect = 1.0;	// live, power of two, driven by the ratchet
	double delta_down = 1.0;
	double delta_across = 1.0;
	bool anytime;
	bool reopen;

	// Best-first-chain ratchet state. Per sweep, the head of each level's beam
	// casts one vote; tallies drive the ratchet at the sweep boundary and reset
	// there. `spinelevel` is the deepest level that has already voted this sweep
	// (each level votes once, levels served in increasing order); reset to -1 at
	// the boundary. `insertedkids` collects the successors of the node currently
	// being expanded (all land in de+1) for the intact-chain test.
	int chainintact = 0;
	int chainbroken = 0;
	int spinelevel = -1;
	std::vector<unsigned long> insertedkids;

	// Rectangle traversal state. `rect[de]` is the h-ordered open list at depth
	// de; `ec[de]` counts expansions taken from it (cumulative across sweeps).
	std::vector<std::set<Entry>> rect;
	std::vector<long> ec;
	int iteration = 1;
	int level = 0;

	std::vector<Node *> seqtonode;	// seq -> node, for erasing/reinserting
	unsigned long nextseq = 0;

	Node *goalnode = NULL;
	bool haveincumbent = false;
	Cost incumbent = Cost(0);
	unsigned long nincumbent = 0;
	bool converged = false;

	ClosedList<Node, Node, D> closed;
	Pool<Node> *nodes;
};
