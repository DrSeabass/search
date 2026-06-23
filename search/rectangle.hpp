// Copyright © 2026 the Search Authors under the MIT license. See AUTHORS for the list of authors.
//
// Rectangle Search: a width-bounded, depth-striated beam search and the
// parent of Triangle Search. One h-ranked open list per depth layer (a vector
// of per-depth min-heaps, best-h popped first). Each iteration expands up to beam_width
// nodes from a layer, then lets deeper layers "catch up" at a rate set by the
// aspect parameter — tracing out a rectangular (vs Triangle's triangular)
// expansion profile. First-solution only (no anytime, no reopening), matching
// the Scorpion reference.
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
#include <queue>
#include <unordered_set>
#include <vector>

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
		for (int i = 0; i < argc; i++) {
			if (i < argc - 1 && strcmp(argv[i], "-width") == 0)
				width = atoi(argv[++i]);
			else if (i < argc - 1 && strcmp(argv[i], "-aspect") == 0)
				aspect = atoi(argv[++i]);
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

		if (d.isgoal(s0)) {
			solpath<D, Node>(d, n0, this->res);
			this->finish();
			return;
		}

		bool solved = false;

		// Expand the root: its successors seed layer 0.
		open.push_back(Layer());
		this->res.expd++;
		{
			State buf, &state = d.unpack(buf, n0->state);
			typename D::Operators ops(d, state);
			for (unsigned int k = 0; k < ops.size() && !solved; k++) {
				if (ops[k] == n0->pop)
					continue;
				this->res.gend++;
				if (considerkid(d, n0, state, ops[k], 0)) {
					solpath<D, Node>(d, goalnode, this->res);
					solved = true;
				}
			}
		}
		if ((int) open.size() == 1)
			open.push_back(Layer());

		while (!solved && !this->limit() && hasnonempty())
			solved = step(d);

		this->finish();
	}

	virtual void reset() {
		SearchAlgorithm<D>::reset();
		open.clear();
		closed.clear();
		depth = 1;
		delete nodes;
		nodes = new Pool<Node>();
	}

	virtual void output(FILE *out) {
		SearchAlgorithm<D>::output(out);
		closed.prstats(stdout, "closed ");
		dfpair(stdout, "open list type", "%s", "vector of (h,seq) min-heaps w/ dedup");
		dfpair(stdout, "node size", "%u", sizeof(Node));
		dfpair(stdout, "beam width", "%d", width);
		dfpair(stdout, "aspect", "%d", aspect);
	}

private:

	bool step(D &d) {
		if ((int) open.size() == 1)
			open.push_back(Layer());

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
				open.push_back(Layer());

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
	// layer i+1. Returns true iff a goal was reached.
	bool selectexpand(D &d, int i) {
		if (i >= (int) open.size() || open[i].empty())
			return false;

		Node *n = popbest(i);

		State buf, &state = d.unpack(buf, n->state);
		if (d.isgoal(state)) {
			solpath<D, Node>(d, n, this->res);
			return true;
		}
		if (n->expanded)
			return false;

		n->expanded = true;
		this->res.expd++;

		while ((int) open.size() <= i + 1)
			open.push_back(Layer());

		typename D::Operators ops(d, state);
		for (unsigned int k = 0; k < ops.size(); k++) {
			if (ops[k] == n->pop)
				continue;
			this->res.gend++;
			if (considerkid(d, n, state, ops[k], i + 1)) {
				solpath<D, Node>(d, goalnode, this->res);
				return true;
			}
		}
		return false;
	}

	// Generate one successor into layer `layer`. Returns true iff it is a goal.
	bool considerkid(D &d, Node *parent, State &state, Oper op, int layer) {
		typename D::Edge e(d, state, op);
		Cost g = parent->g + e.cost;

		// Pack into a fresh node and look it up; destruct it if it is a
		// duplicate (some domains have non-copyable PackedState, so we cannot
		// pack into a temporary and copy — mirror beam.hpp's idiom).
		Node *kid = nodes->construct();
		d.pack(kid->state, e.state);
		unsigned long hash = kid->state.hash(&d);
		Node *dup = static_cast<Node *>(closed.find(kid->state, hash));

		if (dup) {
			this->res.dups++;
			nodes->destruct(kid);
			if (dup->expanded)	// no reopening in Rectangle
				return false;
			if (g < dup->g) {
				dup->g = g;
				dup->parent = parent;
				dup->op = op;
				dup->pop = e.revop;
			}
			insert(layer, dup);
			return false;
		}

		kid->g = g;
		kid->h = d.h(e.state);
		kid->parent = parent;
		kid->op = op;
		kid->pop = e.revop;
		kid->expanded = false;
		closed.add(kid, hash);

		insert(layer, kid);

		// Record the goal only; the caller traces the path once `e` is
		// destructed (some domains apply the operator in place and return a
		// reference to the node's own state — see triangle.hpp).
		if (d.isgoal(e.state)) {
			goalnode = kid;
			return true;
		}
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

	void trim() {
		while (!open.empty() && open.front().empty())
			open.erase(open.begin());
		while (!open.empty() && open.back().empty())
			open.pop_back();
	}

	bool hasnonempty() const {
		for (const Layer &L : open) {
			if (!L.empty())
				return true;
		}
		return false;
	}

	int width;
	int aspect;
	int depth = 1;
	Node *goalnode = NULL;

	std::vector<Layer> open;
	unsigned long seqctr = 0;
	ClosedList<Node, Node, D> closed;
	Pool<Node> *nodes;
};
