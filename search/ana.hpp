// Copyright © 2026 the Search Authors under the MIT license. See AUTHORS for the list of authors.
//
// Anytime Nonparametric A* (ANA*). Eager best-first search that expands the
// open node with the MAXIMAL potential
//
//     e(s) = (G - g(s)) / h(s),
//
// where G is the cost of the current incumbent (initially infinity). The
// ordering needs no weight parameter: with G = infinity the first-solution
// search is maximally greedy (h-only, like GBFS); as G tightens after each
// incumbent, the search automatically re-greedifies toward improving it.
// Nodes with g(s) + h(s) >= G (equivalently e(s) <= 1) cannot improve the
// incumbent and are pruned. Because e(s) depends on G, the open list is
// re-keyed (rebuilt) whenever a new incumbent lowers G (see reorderopen()).
//
// Ported from the Fast Downward / Scorpion implementation. The planning-
// specific pieces (preferred operators, path-dependent evaluators, an
// admissible pruning heuristic, explicit dead-end marking) are dropped: this
// suite's domains expose only h(state), and the mechanism is search-internal.
//
// Reference: van den Berg, Shah, Huang & Goldberg, "Anytime Nonparametric A*",
// AAAI 2011.
#pragma once
#include "../search/search.hpp"
#include "../utils/pool.hpp"
#include <cstring>
#include <cstdlib>
#include <queue>
#include <utility>
#include <vector>

void dfrowhdr(FILE *, const char *, unsigned int ncols, ...);
void dfrow(FILE *, const char *, const char *, ...);
void fatal(const char *, ...);

template <class D> struct AnaSearch : public SearchAlgorithm<D> {

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

	// A lightweight open-list record. We never decrease-key in place; instead
	// we push a fresh entry whenever a node's g improves and treat entries with
	// entry.g > node->g (or pointing at a closed node) as stale, draining them
	// when they surface at the top of the heap.
	struct OpenEntry {
		Node *node;
		Cost g, h;
		OpenEntry() : node(NULL), g(0), h(0) {}
		OpenEntry(Node *n, Cost g, Cost h) : node(n), g(g), h(h) {}
	};

	// Orders entries by potential e(s) = (G - g)/h, HIGHEST first; ties toward
	// lower g; h == 0 yields e = +infinity (top priority). The comparator reads
	// the live incumbent (G and whether one exists) through pointers so a single
	// comparator type serves every rebuild. While no incumbent exists G is
	// infinity, so e is dominated by 1/h and the order is simply greedy (lowest
	// h, then lowest g) — the same maximally-greedy first search GBFS performs.
	//
	// The potential comparison is done by cross-multiplication rather than
	// floating-point division, which avoids the h == 0 divide and the precision
	// loss of forming a ratio. We multiply in double (not in Cost): one of the
	// suite's Cost types (gridnav) is a class with operator double() but no
	// operator*, and the products here stay far below 2^53 for every domain, so
	// the double arithmetic is exact for the integer/float Cost types and is the
	// native representation for gridnav's already-double cost value.
	struct OpenEntryCompare {
		const bool *have;
		const Cost *bound;

		// std::priority_queue pops the GREATEST element, so return true when lhs
		// has LOWER priority than rhs (i.e. lhs should be expanded after rhs).
		bool operator()(const OpenEntry &lhs, const OpenEntry &rhs) const {
			if (!*have) {
				// G = infinity: greedy order (lowest h, then lowest g). h == 0 is
				// the smallest h, so it naturally rises to the top.
				if (lhs.h != rhs.h)
					return lhs.h > rhs.h;
				return lhs.g > rhs.g;
			}
			const bool lhs_inf = (lhs.h == Cost(0));
			const bool rhs_inf = (rhs.h == Cost(0));
			if (lhs_inf || rhs_inf) {
				if (lhs_inf && rhs_inf)
					return lhs.g > rhs.g;
				// Exactly one has e = +infinity; the finite one ranks lower.
				return !lhs_inf;
			}
			// Both finite with h > 0: e(lhs) < e(rhs)
			// <=> (G - lhs.g) / lhs.h < (G - rhs.g) / rhs.h
			// <=> (G - lhs.g) * rhs.h < (G - rhs.g) * lhs.h  (h values > 0).
			const double G = (double) *bound;
			const double lhs_key = (G - (double) lhs.g) * (double) rhs.h;
			const double rhs_key = (G - (double) rhs.g) * (double) lhs.h;
			if (lhs_key != rhs_key)
				return lhs_key < rhs_key;
			return lhs.g > rhs.g;
		}
	};

	typedef std::priority_queue<OpenEntry, std::vector<OpenEntry>, OpenEntryCompare> OpenList;

	AnaSearch(int argc, const char *argv[]) :
			SearchAlgorithm<D>(argc, argv), closed(30000001),
			open(OpenEntryCompare{&haveincumbent, &incumbent}) {
		anytime = false;
		reopen = true;
		for (int i = 0; i < argc; i++) {
			if (strcmp(argv[i], "-anytime") == 0)
				anytime = true;
			else if (strcmp(argv[i], "-noreopen") == 0)
				reopen = false;
		}
		nodes = new Pool<Node>();
	}

	virtual ~AnaSearch() {
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

		if (d.isgoal(s0)) {
			updateincumbent(d, n0);
			if (!anytime) {
				this->finish();
				return;
			}
		} else {
			open.push(OpenEntry(n0, n0->g, n0->h));
		}

		bool done = false;
		while (!this->limit() && !done) {
			Node *n = poptop();
			if (!n) {
				// Open exhausted. If we hold an incumbent, every node was pruned
				// by g + h >= G, so none can beat it: it is proven optimal.
				if (haveincumbent)
					converged = true;
				break;
			}
			done = expand(d, n);
		}

		this->finish();
	}

	virtual void reset() {
		SearchAlgorithm<D>::reset();
		open = OpenList(OpenEntryCompare{&haveincumbent, &incumbent});
		closed.clear();
		haveincumbent = false;
		incumbent = Cost(0);
		nincumbent = 0;
		converged = false;
		goalnode = NULL;
		delete nodes;
		nodes = new Pool<Node>();
	}

	virtual void output(FILE *out) {
		SearchAlgorithm<D>::output(out);
		closed.prstats(stdout, "closed ");
		dfpair(stdout, "open list type", "%s", "potential-ordered binary heap");
		dfpair(stdout, "node size", "%u", sizeof(Node));
		dfpair(stdout, "anytime", "%s", anytime ? "true" : "false");
		dfpair(stdout, "reopen closed", "%s", reopen ? "true" : "false");
		dfpair(stdout, "converged", "%s", converged ? "yes" : "no");
	}

protected:

	// Pop the highest-potential eligible node, draining stale entries (a cheaper
	// path was found, or the node is closed) and any that the current bound
	// prunes (g + h >= G). NULL when nothing eligible remains.
	Node *poptop() {
		while (!open.empty()) {
			OpenEntry e = open.top();
			open.pop();
			Node *n = e.node;
			if (e.g > n->g || n->status == CLOSED)
				continue;
			if (haveincumbent && n->g + n->h >= incumbent)
				continue;
			return n;
		}
		return NULL;
	}

	// Close `n` and route its successors back onto the open list. Returns true
	// iff the search should stop (first-solution goal in non-anytime mode).
	bool expand(D &d, Node *n) {
		n->status = CLOSED;
		this->res.expd++;
		State buf, &state = d.unpack(buf, n->state);
		typename D::Operators ops(d, state);
		for (unsigned int k = 0; k < ops.size(); k++) {
			if (ops[k] == n->pop)
				continue;
			this->res.gend++;
			if (considerkid(d, n, state, ops[k])) {
				// Edge is out of scope now; tracing the path is safe.
				bool improved = updateincumbent(d, goalnode);
				if (!anytime)
					return true;	// first solution
				// G changed: re-key the open list before inserting anything else.
				if (improved)
					reorderopen();
			}
		}
		return false;
	}

	// Generate one successor. Returns true iff it is a goal (the caller records
	// the incumbent once the Edge `e` is out of scope — some domains apply the
	// operator in place and hand back a reference to the node's own stored
	// state, so tracing a path while `e` is live would read mutated states).
	bool considerkid(D &d, Node *parent, State &state, Oper op) {
		typename D::Edge e(d, state, op);
		Cost g = parent->g + e.cost;

		// g-only bound pruning: once we hold an incumbent, a successor whose g
		// already meets or exceeds it cannot improve on it (subsumes the full
		// g + h >= G test below for the common case and is cheaper).
		if (haveincumbent && g >= incumbent)
			return false;

		// Pack into a fresh node and look it up; destruct it if it is a duplicate
		// (some domains have non-copyable PackedState, so we cannot pack into a
		// temporary and copy — mirror beam.hpp / triangle's idiom).
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
			if (targetisskipped(dup, g))
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
		// once `e` is destructed (see considerkid's contract above).
		if (d.isgoal(e.state)) {
			goalnode = target;
			return true;
		}

		// ANA* line 13: keep s only if it can still improve the incumbent.
		if (haveincumbent && target->g + target->h >= incumbent)
			return false;

		open.push(OpenEntry(target, target->g, target->h));
		return false;
	}

	// A duplicate is skipped (no re-expansion path) when reopening is off, or
	// when it is closed and the new path is not strictly cheaper.
	bool targetisskipped(Node *dup, Cost g) {
		if (!reopen)
			return dup->status == CLOSED;
		if (dup->status == CLOSED && g >= dup->g)
			return true;
		return false;
	}

	// Re-key the open list after the incumbent bound G has changed. Each entry's
	// potential e(s) = (G - g)/h shifts with G, so the heap must be rebuilt;
	// while rebuilding we drop entries that became stale, closed, or that the
	// tightened bound now prunes (g + h >= G, i.e. e(s) <= 1).
	void reorderopen() {
		std::vector<OpenEntry> kept;
		kept.reserve(open.size());
		while (!open.empty()) {
			OpenEntry e = open.top();
			open.pop();
			Node *n = e.node;
			if (e.g > n->g || n->status == CLOSED)
				continue;
			if (haveincumbent && n->g + n->h >= incumbent)
				continue;
			kept.push_back(e);
		}
		open = OpenList(OpenEntryCompare{&haveincumbent, &incumbent}, std::move(kept));
	}

	// Record `goal` as the incumbent if it is strictly cheaper than the current
	// one. Returns true iff the incumbent improved (so the caller re-keys open).
	bool updateincumbent(D &d, Node *goal) {
		Cost c = goal->g;
		if (haveincumbent && !(c < incumbent))
			return false;
		incumbent = c;
		haveincumbent = true;
		solpath<D, Node>(d, goal, this->res);
		nincumbent++;
		dfrow(stdout, "incumbent", "uuugg", nincumbent, this->res.expd,
			this->res.gend, (double) c, walltime() - this->res.wallstart);
		return true;
	}

	void rowhdr() {
		dfrowhdr(stdout, "incumbent", 5, "num", "nodes expanded",
			"nodes generated", "solution cost", "wall time");
	}

	bool anytime;
	bool reopen;

	bool haveincumbent = false;
	Cost incumbent = Cost(0);
	unsigned long nincumbent = 0;
	bool converged = false;
	Node *goalnode = NULL;

	ClosedList<Node, Node, D> closed;
	OpenList open;
	Pool<Node> *nodes;
};
