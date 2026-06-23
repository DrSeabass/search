// Copyright © 2026 the Search Authors under the MIT license. See AUTHORS for the list of authors.
//
// Triangle Search: an anytime, depth-striated beam search.
//
// One ranked (h-then-g) open list per depth layer, held in a deque indexed
// from the current frontier. Each iteration cascades from layer 0 up to
// (max active layer + slope), expanding at most one node per layer; successors
// of a layer-i node go into layer i+1. This reproduces the triangular
// expansion profile that gives the algorithm its name.
//
// Ported from the Fast Downward / Scorpion implementation
// (src/search/search_algorithms/triangle_search.cc). The planning-specific
// pieces — preferred operators, path-dependent evaluators, an admissible
// pruning heuristic, and explicit dead-end marking — are dropped: this suite's
// domains expose only h(state), and the mechanism is purely search-internal.
//
// Reference: Lemons, Ruml, Linares López, Holte. "Triangle Search: An Anytime
// Beam Search." ICAPS 2023 HSDIP Workshop (arXiv:2312.12554).
#pragma once
#include "../search/search.hpp"
#include "../utils/pool.hpp"
#include <cstring>
#include <cstdlib>
#include <deque>
#include <queue>
#include <utility>
#include <vector>

void dfrowhdr(FILE *, const char *, unsigned int ncols, ...);
void dfrow(FILE *, const char *, const char *, ...);
void fatal(const char *, ...);

template <class D> struct TriangleSearch : public SearchAlgorithm<D> {

	typedef typename D::State State;
	typedef typename D::PackedState PackedState;
	typedef typename D::Cost Cost;
	typedef typename D::Oper Oper;

	enum { OPEN, CLOSED };

	struct Node {
		PackedState state;
		Node *parent;
		Oper op, pop;
		Cost g, h;
		char status;

		Node() : parent(NULL), status(OPEN) {
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

	// A lightweight open-list record. We never decrease-key inside a layer;
	// instead we push a fresh entry whenever a node's g improves and treat
	// entries with entry.g > node->g (or pointing at a closed node) as stale,
	// draining them when they surface at the top of a layer.
	struct OpenEntry {
		Node *node;
		Cost h, g;
		OpenEntry() : node(NULL), h(0), g(0) {}
		OpenEntry(Node *n, Cost h, Cost g) : node(n), h(h), g(g) {}
	};

	// std::priority_queue pops the "greatest" element under this comparator,
	// so returning true when lhs is *worse* puts the lowest-h (then lowest-g)
	// entry on top — a greedy, h-ranked layer.
	struct OpenEntryCompare {
		bool operator()(const OpenEntry &lhs, const OpenEntry &rhs) const {
			if (lhs.h != rhs.h)
				return lhs.h > rhs.h;
			return lhs.g > rhs.g;
		}
	};

	typedef std::priority_queue<OpenEntry, std::vector<OpenEntry>, OpenEntryCompare> Layer;

	TriangleSearch(int argc, const char *argv[]) :
		SearchAlgorithm<D>(argc, argv), closed(30000001) {
		slope = 1;
		reopen = true;
		anytime = false;
		for (int i = 0; i < argc; i++) {
			if (i < argc - 1 && strcmp(argv[i], "-slope") == 0)
				slope = atoi(argv[++i]);
			else if (strcmp(argv[i], "-anytime") == 0)
				anytime = true;
			else if (strcmp(argv[i], "-noreopen") == 0)
				reopen = false;
		}

		if (slope < 1)
			fatal("Must specify a >0 slope using -slope");

		nodes = new Pool<Node>();
	}

	~TriangleSearch() {
		delete nodes;
	}

	void search(D &d, typename D::State &s0) {
		rowhdr();
		this->start();
		closed.init(d);

		Node *n0 = nodes->construct();
		d.pack(n0->state, s0);
		n0->g = Cost(0);
		n0->h = d.h(s0);
		n0->op = n0->pop = D::Nop;
		n0->parent = NULL;
		n0->status = OPEN;
		closed.add(n0, n0->state.hash(&d));

		open.emplace_back();
		maxactive = 0;

		if (d.isgoal(s0)) {
			updateincumbent(d, n0);
			if (!anytime) {
				this->finish();
				return;
			}
		} else {
			open[0].push(OpenEntry(n0, n0->h, n0->g));
		}

		bool done = false;
		while (!this->limit() && !done) {
			while (!open.empty() && open.front().empty()) {
				// Recycle the emptied front layer (keeps its backing vector's
				// capacity) instead of freeing it; the frontier advances every
				// step, so this avoids a malloc/free per layer traversed.
				layerpool.push_back(std::move(open.front()));
				open.pop_front();
				--maxactive;
			}
			if (maxactive < 0)
				maxactive = 0;
			if (open.empty())
				break;

			// Cascade from the frontier up to maxactive+slope; the deque grows
			// lazily as successors are inserted rather than being pre-extended.
			const int cap = maxactive + slope;
			for (int i = 0; i < cap && !this->limit(); i++) {
				if (i >= (int) open.size())
					break;
				if (open[i].empty())
					continue;

				Node *n = popeligible(i);
				if (!n)
					continue;

				n->status = CLOSED;
				this->res.expd++;

				State buf, &state = d.unpack(buf, n->state);
				typename D::Operators ops(d, state);
				for (unsigned int k = 0; k < ops.size(); k++) {
					if (ops[k] == n->pop)
						continue;
					this->res.gend++;
					if (considerkid(d, n, state, ops[k], i + 1)) {
						// Edge is now out of scope; tracing the path is safe.
						updateincumbent(d, goalnode);
						if (!anytime) {
							done = true;	// first solution
							break;
						}
					}
				}
				if (done)
					break;
			}
		}

		this->finish();
	}

	virtual void reset() {
		SearchAlgorithm<D>::reset();
		open.clear();
		layerpool.clear();
		closed.clear();
		maxactive = -1;
		haveincumbent = false;
		nincumbent = 0;
		delete nodes;
		nodes = new Pool<Node>();
	}

	virtual void output(FILE *out) {
		SearchAlgorithm<D>::output(out);
		closed.prstats(stdout, "closed ");
		dfpair(stdout, "open list type", "%s", "deque of h-ranked heaps");
		dfpair(stdout, "node size", "%u", sizeof(Node));
		dfpair(stdout, "slope", "%d", slope);
		dfpair(stdout, "anytime", "%s", anytime ? "true" : "false");
		dfpair(stdout, "reopen closed", "%s", reopen ? "true" : "false");
	}

private:

	// Drain stale/closed entries from the top of layer i and return the first
	// expandable node (popped), or NULL if the layer holds nothing eligible.
	Node *popeligible(int i) {
		while (!open[i].empty()) {
			OpenEntry e = open[i].top();
			Node *n = e.node;
			bool stale = (e.g > n->g) || (n->status == CLOSED);
			open[i].pop();
			if (open[i].empty() && i == maxactive)
				recomputemaxactive();
			if (!stale)
				return n;
		}
		return NULL;
	}

	void recomputemaxactive() {
		while (maxactive >= 0 &&
		       (maxactive >= (int) open.size() || open[maxactive].empty()))
			--maxactive;
	}

	void insert(int layer, Node *n) {
		while (layer >= (int) open.size())
			growback();
		open[layer].push(OpenEntry(n, n->h, n->g));
		if (layer > maxactive)
			maxactive = layer;
	}

	// Append one layer, reusing a recycled (empty, capacity-retaining) layer
	// from the pool when available rather than allocating a fresh heap.
	void growback() {
		if (!layerpool.empty()) {
			open.push_back(std::move(layerpool.back()));
			layerpool.pop_back();
		} else {
			open.emplace_back();
		}
	}

	// Generate one successor. Returns true iff a solution was found and the
	// search should stop (goal reached in non-anytime mode).
	bool considerkid(D &d, Node *parent, State &state, Oper op, int layer) {
		typename D::Edge e(d, state, op);
		Cost g = parent->g + e.cost;

		// g-only bound pruning: once we hold an incumbent, a successor whose g
		// already meets or exceeds it cannot improve on it.
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
			kid->status = OPEN;
			closed.add(kid, hash);
			target = kid;
		} else {
			this->res.dups++;
			nodes->destruct(kid);
			if (target_is_skipped(dup, g))
				return false;
			if (dup->status == CLOSED) {	// reopen via a cheaper path
				dup->g = g;
				dup->parent = parent;
				dup->op = op;
				dup->pop = e.revop;
				dup->status = OPEN;
				this->res.reopnd++;
			} else if (g < dup->g) {	// improve an open node's path
				dup->g = g;
				dup->parent = parent;
				dup->op = op;
				dup->pop = e.revop;
			}
			target = dup;
		}

		// Goal check applies to every retained successor (new, reopened, or
		// re-seen open) so re-reaching the goal more cheaply improves the
		// incumbent — this is what makes the anytime mode converge. We only
		// record the goal node here; the caller runs solpath()/updateincumbent
		// once `e` is destructed, because some domains (e.g. pancake) apply the
		// operator in place and hand back a reference to the node's own stored
		// state — tracing the path while `e` is live would read mutated states.
		if (d.isgoal(e.state)) {
			goalnode = target;
			return true;
		}

		insert(layer, target);
		return false;
	}

	// A duplicate is skipped (no re-expansion path) when reopening is off, or
	// when it is closed and the new path is not strictly cheaper.
	bool target_is_skipped(Node *dup, Cost g) {
		if (!reopen)
			return true;
		if (dup->status == CLOSED && g >= dup->g)
			return true;
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

	int slope;
	bool anytime;
	bool reopen;

	std::deque<Layer> open;
	std::vector<Layer> layerpool;	// recycled empty layers (retain capacity)
	int maxactive = -1;

	bool haveincumbent = false;
	Cost incumbent = Cost(0);
	unsigned long nincumbent = 0;
	Node *goalnode = NULL;

	ClosedList<Node, Node, D> closed;
	Pool<Node> *nodes;
};
