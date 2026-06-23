// Copyright © 2026 the Search Authors under the MIT license. See AUTHORS for the list of authors.
//
// Rectangle Search: a width-bounded, depth-striated beam search and the
// parent of Triangle Search. One h-ranked open list per depth layer (a vector
// of per-depth min-heaps, best-h popped first). Each iteration expands up to beam_width
// nodes from a layer, then lets deeper layers "catch up" at a rate set by the
// aspect parameter — tracing out a rectangular (vs Triangle's triangular)
// expansion profile. Stops at the first solution unless anytime=true, in which
// case it keeps improving the incumbent and (reopening closed nodes reached by
// a cheaper path, with g-bound pruning) converges to the optimal cost.
//
// Ported from src/search/search_algorithms/rectangle_search.cc; the
// planning-specific machinery (path-dependent evaluators, pruning method,
// dead-end marking) is dropped — this suite exposes only h(state).
//
// Reference: Lemons, Ruml, Holte, Linares López. "Rectangle Search: An Anytime
// Beam Search." AAAI 2024.
#pragma once
#include "../search/search.hpp"
#include "../utils/pool.hpp"
#include <cstring>
#include <cstdlib>
#include <deque>
#include <queue>
#include <unordered_set>
#include <utility>
#include <vector>

void dfrowhdr(FILE *, const char *, unsigned int ncols, ...);
void dfrow(FILE *, const char *, const char *, ...);
void fatal(const char *, ...);

template <class D> struct RectangleSearch : public SearchAlgorithm<D> {

	typedef typename D::State State;
	typedef typename D::PackedState PackedState;
	typedef typename D::Cost Cost;
	typedef typename D::Oper Oper;

	struct Node {
		PackedState state;
		Node *parent;
		Oper op, pop;
		Cost g, h;
		bool expanded;

		Node() : parent(NULL), expanded(false) {
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

	// A depth layer's open list. Originally a deque kept sorted by h, which made
	// both the duplicate check and the sorted insert O(layer size) -- quadratic
	// on high-branching domains. We keep the exact same pop order (lowest h
	// first; among equal h, the most recently inserted first) with an (h, seq)
	// min-heap, and make the duplicate check O(1) with a membership set. seq is
	// a monotonic insertion counter, so "largest seq among equal h" reproduces
	// the old "inserted before existing equal-h entries" tie-break.
	struct HeapEntry {
		Cost h;
		unsigned long seq;
		Node *node;
	};
	struct HeapLess {
		bool operator()(const HeapEntry &a, const HeapEntry &b) const {
			if (a.h != b.h)
				return a.h > b.h;	// smallest h on top
			return a.seq < b.seq;	// ties: most recently inserted on top
		}
	};
	struct Layer {
		std::priority_queue<HeapEntry, std::vector<HeapEntry>, HeapLess> heap;
		std::unordered_set<Node *> members;
		bool empty() const { return heap.empty(); }
	};

	RectangleSearch(int argc, const char *argv[]) :
		SearchAlgorithm<D>(argc, argv), closed(30000001) {
		width = 100;
		aspect = 1;
		anytime = false;
		reopen = true;
		for (int i = 0; i < argc; i++) {
			if (i < argc - 1 && strcmp(argv[i], "-width") == 0)
				width = atoi(argv[++i]);
			else if (i < argc - 1 && strcmp(argv[i], "-aspect") == 0)
				aspect = atoi(argv[++i]);
			else if (strcmp(argv[i], "-anytime") == 0)
				anytime = true;
			else if (strcmp(argv[i], "-noreopen") == 0)
				reopen = false;
		}

		if (width < 1)
			fatal("Must specify a >0 beam width using -width");
		if (aspect < 1)
			fatal("Must specify a >0 aspect using -aspect");

		nodes = new Pool<Node>();
	}

	~RectangleSearch() {
		delete nodes;
	}

	void search(D &d, typename D::State &s0) {
		rowhdr();
		this->start();
		closed.init(d);
		depth = 1;

		Node *n0 = nodes->construct();
		d.pack(n0->state, s0);
		n0->g = Cost(0);
		n0->h = d.h(s0);
		n0->op = n0->pop = D::Nop;
		n0->parent = NULL;
		n0->expanded = true;
		closed.add(n0, n0->state.hash(&d));

		if (d.isgoal(s0)) {	// start == goal: cost 0 is trivially optimal
			updateincumbent(d, n0);
			this->finish();
			return;
		}

		bool done = false;

		// Expand the root: its successors seed layer 0.
		growback();
		this->res.expd++;
		{
			State buf, &state = d.unpack(buf, n0->state);
			typename D::Operators ops(d, state);
			for (unsigned int k = 0; k < ops.size() && !done; k++) {
				if (ops[k] == n0->pop)
					continue;
				this->res.gend++;
				if (considerkid(d, n0, state, ops[k], 0)) {
					updateincumbent(d, goalnode);
					if (!anytime)
						done = true;	// first solution
				}
			}
		}
		if ((int) open.size() == 1)
			growback();

		while (!done && !this->limit() && hasnonempty())
			done = step(d);

		// In anytime mode the loop ends either because a limit was hit or
		// because the open layers were exhausted; the latter (with an incumbent
		// in hand) proves the incumbent optimal.
		converged = anytime && haveincumbent && !this->limit();

		this->finish();
	}

	virtual void reset() {
		SearchAlgorithm<D>::reset();
		open.clear();
		layerpool.clear();
		closed.clear();
		depth = 1;
		haveincumbent = false;
		nincumbent = 0;
		converged = false;
		delete nodes;
		nodes = new Pool<Node>();
	}

	virtual void output(FILE *out) {
		SearchAlgorithm<D>::output(out);
		closed.prstats(stdout, "closed ");
		dfpair(stdout, "open list type", "%s", "deque of (h,seq) min-heaps w/ dedup");
		dfpair(stdout, "node size", "%u", sizeof(Node));
		dfpair(stdout, "beam width", "%d", width);
		dfpair(stdout, "aspect", "%d", aspect);
		dfpair(stdout, "anytime", "%s", anytime ? "true" : "false");
		dfpair(stdout, "reopen closed", "%s", reopen ? "true" : "false");
		dfpair(stdout, "converged", "%s", converged ? "yes" : "no");
	}

private:

	bool step(D &d) {
		if ((int) open.size() == 1)
			growback();

		const int initial = (int) open.size();
		for (int i = 0; i < initial - 1; i++) {
			for (int w = 0; w < width; w++) {
				if (open[i].empty())
					break;
				if (selectexpand(d, i))
					return true;
				if (this->limit())
					return false;
			}

			for (int a = 0; a < aspect; a++)
				growback();

			const int cur = (int) open.size();
			for (int j = i + 1; j < cur - 1; j++) {
				for (int k = 0; k < depth; k++) {
					for (int w = 0; w < width; w++) {
						if (open[j].empty())
							break;
						if (selectexpand(d, j))
							return true;
						if (this->limit())
							return false;
					}
				}
			}
		}

		depth += aspect;
		trim();
		return false;
	}

	// Pop the best-h node from layer i and expand it, routing successors into
	// layer i+1. Returns true iff the search should stop (first solution in
	// non-anytime mode). Goals are recorded as incumbents, never inserted, so a
	// popped node is always an expandable non-goal (or an already-closed dup).
	bool selectexpand(D &d, int i) {
		if (i >= (int) open.size() || open[i].empty())
			return false;

		Node *n = popbest(i);
		if (n->expanded)	// stale cross-layer entry for a closed node
			return false;

		n->expanded = true;
		this->res.expd++;

		State buf, &state = d.unpack(buf, n->state);
		while ((int) open.size() <= i + 1)
			growback();

		typename D::Operators ops(d, state);
		for (unsigned int k = 0; k < ops.size(); k++) {
			if (ops[k] == n->pop)
				continue;
			this->res.gend++;
			if (considerkid(d, n, state, ops[k], i + 1)) {
				// Edge is out of scope now; tracing the path is safe.
				updateincumbent(d, goalnode);
				if (!anytime)
					return true;	// first solution
			}
		}
		return false;
	}

	// Generate one successor into layer `layer`. Returns true iff it is a goal
	// (the caller records the incumbent once the Edge is out of scope).
	bool considerkid(D &d, Node *parent, State &state, Oper op, int layer) {
		typename D::Edge e(d, state, op);
		Cost g = parent->g + e.cost;

		// g-only bound pruning: once we hold an incumbent, a successor whose g
		// already meets or exceeds it cannot improve on it. (g is monotone, so
		// this is safe and lets the anytime search converge to the optimum.)
		if (haveincumbent && g >= incumbent)
			return false;

		// Pack into a fresh node and look it up; destruct it if it is a
		// duplicate (some domains have non-copyable PackedState, so we cannot
		// pack into a temporary and copy — mirror beam.hpp's idiom).
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
			closed.add(kid, hash);
			target = kid;
		} else {
			this->res.dups++;
			nodes->destruct(kid);
			if (dup->expanded) {
				// Reopen a closed node reached by a strictly cheaper path so
				// the corrected g propagates to its successors. Without this,
				// depth-striped search (layer = #operators, not cost) commits
				// to the first path and cannot reach the optimum in non-unit
				// domains.
				if (!reopen || g >= dup->g)
					return false;
				dup->g = g;
				dup->parent = parent;
				dup->op = op;
				dup->pop = e.revop;
				dup->expanded = false;
				this->res.reopnd++;
			} else if (g < dup->g) {	// improve a still-open node's path
				dup->g = g;
				dup->parent = parent;
				dup->op = op;
				dup->pop = e.revop;
			}
			target = dup;
		}

		// Record the goal only; the caller traces the path once `e` is
		// destructed (some domains apply the operator in place and return a
		// reference to the node's own state — see triangle.hpp). Goals are
		// never inserted into a layer.
		if (d.isgoal(e.state)) {
			goalnode = target;
			return true;
		}

		insert(layer, target);
		return false;
	}

	// Insert into a layer, skipping duplicates (a state maps to one Node, so
	// pointer identity is state identity). O(1) dedup + O(log size) push.
	void insert(int layer, Node *n) {
		Layer &L = open[layer];
		if (!L.members.insert(n).second)	// already in this layer
			return;
		L.heap.push(HeapEntry{n->h, seqctr++, n});
	}

	// Remove and return the best-h node from layer i (lowest h, then most
	// recently inserted) -- the old sorted deque's front().
	Node *popbest(int i) {
		Layer &L = open[i];
		Node *n = L.heap.top().node;
		L.heap.pop();
		L.members.erase(n);
		return n;
	}

	// Append one layer, reusing a recycled (empty, capacity-retaining) layer
	// from the pool when available rather than allocating a fresh heap + hash
	// table. Layers turn over every step, so this avoids that churn.
	void growback() {
		if (!layerpool.empty()) {
			open.push_back(std::move(layerpool.back()));
			layerpool.pop_back();
		} else {
			open.emplace_back();
		}
	}

	void trim() {
		// Recycle emptied front/back layers instead of freeing them. open is a
		// deque, so dropping the front is O(1) (the old vector::erase(begin())
		// moved every remaining layer down each step).
		while (!open.empty() && open.front().empty()) {
			layerpool.push_back(std::move(open.front()));
			open.pop_front();
		}
		while (!open.empty() && open.back().empty()) {
			layerpool.push_back(std::move(open.back()));
			open.pop_back();
		}
	}

	bool hasnonempty() const {
		for (const Layer &L : open) {
			if (!L.empty())
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

	int width;
	int aspect;
	bool anytime;
	bool reopen;
	int depth = 1;
	Node *goalnode = NULL;

	bool haveincumbent = false;
	Cost incumbent = Cost(0);
	unsigned long nincumbent = 0;
	bool converged = false;

	std::deque<Layer> open;
	std::vector<Layer> layerpool;	// recycled empty layers (retain capacity)
	unsigned long seqctr = 0;
	ClosedList<Node, Node, D> closed;
	Pool<Node> *nodes;
};
