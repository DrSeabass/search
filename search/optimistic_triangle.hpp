// Copyright © 2026 the Search Authors under the MIT license. See AUTHORS.
//
// Optimistic bounded-suboptimal Triangle Search.  A cleanup queue ordered by
// admissible f and the depth-stratified Triangle queues contain exactly the
// same live nodes.  A meta-controller serves them in three regimes:
//
//   1. A* only, until (g(f_min) / f_min) * w^k > 1;
//   2. Triangle only, until an incumbent is found;
//   3. round robin: one A* expansion, then one Triangle cascade.
//
// The search stops as soon as incumbent <= w * f_min.  Triangle uses a fixed
// slope and, within a depth, orders nodes by h then g.
#pragma once

#include "../search/search.hpp"
#include "../utils/pool.hpp"

#include <cmath>
#include <cstring>
#include <cstdlib>
#include <deque>
#include <queue>
#include <vector>

void dfrowhdr(FILE *, const char *, unsigned int ncols, ...);
void dfrow(FILE *, const char *, const char *, ...);
void fatal(const char *, ...);

template <class D> struct OptimisticTriangleSearch : public SearchAlgorithm<D> {
    typedef typename D::State State;
    typedef typename D::PackedState PackedState;
    typedef typename D::Cost Cost;
    typedef typename D::Oper Oper;

    enum Status { OPEN, CLOSED };
    enum Phase { ASTAR_ONLY, TRIANGLE_ONLY, ROUND_ROBIN };

    struct Node {
        PackedState state;
        Node *parent;
        Oper op, pop;
        Cost g, h;
        int depth;
        Status status;

        Node() : parent(NULL), depth(0), status(OPEN) {}

        static ClosedEntry<Node, D> &closedentry(Node *n) { return n->closedent; }
        static PackedState &key(Node *n) { return n->state; }

    private:
        ClosedEntry<Node, D> closedent;
    };

    struct Entry {
        Node *node;
        Cost g;
        int depth;
        Entry() : node(NULL), g(0), depth(0) {}
        Entry(Node *n) : node(n), g(n->g), depth(n->depth) {}
    };

    struct FCompare {
        bool operator()(const Entry &a, const Entry &b) const {
            Cost af = a.g + a.node->h;
            Cost bf = b.g + b.node->h;
            if (af != bf)
                return af > bf;
            return a.g < b.g; // A*: prefer larger g on an f tie.
        }
    };

    struct TriangleCompare {
        bool operator()(const Entry &a, const Entry &b) const {
            if (a.node->h != b.node->h)
                return a.node->h > b.node->h;
            return a.g > b.g;
        }
    };

    typedef std::priority_queue<Entry, std::vector<Entry>, FCompare> FQueue;
    typedef std::priority_queue<Entry, std::vector<Entry>, TriangleCompare> Layer;

    OptimisticTriangleSearch(int argc, const char *argv[]) :
        SearchAlgorithm<D>(argc, argv), closed(30000001), nodes(new Pool<Node>()) {
        slope = 1;
        weight = -1.0;
        exponent = -1.0;
        reopen = true;
        for (int i = 0; i < argc; ++i) {
            if (i < argc - 1 && strcmp(argv[i], "-slope") == 0)
                slope = atoi(argv[++i]);
            else if (i < argc - 1 && strcmp(argv[i], "-w") == 0)
                weight = strtod(argv[++i], NULL);
            else if (i < argc - 1 && strcmp(argv[i], "-k") == 0)
                exponent = strtod(argv[++i], NULL);
            else if (strcmp(argv[i], "-noreopen") == 0)
                reopen = false;
        }
        if (slope < 1)
            fatal("Must specify a >0 slope using -slope");
        if (!(weight >= 1.0) || !std::isfinite(weight))
            fatal("Must specify a finite weight >=1 using -w");
        if (!(exponent > 0.0) || !std::isfinite(exponent))
            fatal("Must specify a finite exponent >0 using -k");
    }

    ~OptimisticTriangleSearch() { delete nodes; }

    void search(D &d, State &s0) {
        rowhdr();
        this->start();
        closed.init(d);
        phase = ASTAR_ONLY;
        rr_cleanup_turns = rr_triangle_turns = 0;
        switched = false;
        switch_expansions = 0;
        switch_f = switch_g = 0.0;

        Node *root = nodes->construct();
        d.pack(root->state, s0);
        root->parent = NULL;
        root->op = root->pop = D::Nop;
        root->g = Cost(0);
        root->h = d.h(s0);
        root->depth = 0;
        root->status = OPEN;
        closed.add(root, root->state.hash(&d));

        if (d.isgoal(s0)) {
            updateincumbent(d, root);
        } else {
            insert(root);
        }

        while (!this->limit()) {
            Node *fmin = peekf();
            if (!fmin)
                break;
            if (certified(fmin))
                break;

            if (haveincumbent)
                phase = ROUND_ROBIN;
            else if (phase == ASTAR_ONLY && switch_to_triangle(fmin)) {
                switched = true;
                switch_expansions = this->res.expd;
                switch_g = static_cast<double>(fmin->g);
                switch_f = static_cast<double>(fmin->g + fmin->h);
                phase = TRIANGLE_ONLY;
            }

            if (phase == ASTAR_ONLY) {
                if (!expand_cleanup(d))
                    break;
            } else if (phase == TRIANGLE_ONLY) {
                if (!triangle_cascade(d))
                    break;
            } else {
                ++rr_cleanup_turns;
                if (!expand_cleanup(d))
                    break;
                fmin = peekf();
                if (!fmin || certified(fmin) || this->limit())
                    break;
                ++rr_triangle_turns;
                if (!triangle_cascade(d))
                    break;
            }
        }

        Node *fmin = peekf();
        proved_bound = haveincumbent && (!fmin || certified(fmin));
        this->finish();
    }

    void reset() {
        SearchAlgorithm<D>::reset();
        cleanup = FQueue();
        layers.clear();
        closed.clear();
        delete nodes;
        nodes = new Pool<Node>();
        haveincumbent = false;
        proved_bound = false;
        incumbent = Cost(0);
        nincumbent = 0;
    }

    void output(FILE *out) {
        SearchAlgorithm<D>::output(out);
        closed.prstats(out, "closed ");
        dfpair(out, "open list type", "%s", "synchronized f and triangle heaps");
        dfpair(out, "node size", "%u", sizeof(Node));
        dfpair(out, "weight", "%g", weight);
        dfpair(out, "slope", "%d", slope);
        dfpair(out, "switch exponent", "%g", exponent);
        dfpair(out, "switched to triangle", "%s", switched ? "yes" : "no");
        dfpair(out, "switch nodes expanded", "%lu", switch_expansions);
        dfpair(out, "switch f min g", "%g", switch_g);
        dfpair(out, "switch f min f", "%g", switch_f);
        dfpair(out, "reopen closed", "%s", reopen ? "true" : "false");
        dfpair(out, "proved within bound", "%s", proved_bound ? "yes" : "no");
        dfpair(out, "round robin cleanup turns", "%lu", rr_cleanup_turns);
        dfpair(out, "round robin triangle turns", "%lu", rr_triangle_turns);
    }

private:
    bool stale(const Entry &e) const {
        return e.node->status == CLOSED || e.g != e.node->g ||
            e.depth != e.node->depth;
    }

    Node *peekf() {
        while (!cleanup.empty() && stale(cleanup.top()))
            cleanup.pop();
        return cleanup.empty() ? NULL : cleanup.top().node;
    }

    Node *popf() {
        Node *n = peekf();
        if (n)
            cleanup.pop();
        return n;
    }

    Node *poptriangle(int depth) {
        Layer &layer = layers[depth];
        while (!layer.empty() && stale(layer.top()))
            layer.pop();
        if (layer.empty())
            return NULL;
        Node *n = layer.top().node;
        layer.pop();
        return n;
    }

    void insert(Node *n) {
        while (n->depth >= static_cast<int>(layers.size()))
            layers.emplace_back();
        Entry e(n);
        cleanup.push(e);
        layers[n->depth].push(e);
    }

    bool switch_to_triangle(Node *fmin) const {
        double f = static_cast<double>(fmin->g + fmin->h);
        if (!(f > 0.0))
            return false;
        double ratio = static_cast<double>(fmin->g) / f;
        return ratio * std::pow(weight, exponent) > 1.0;
    }

    bool certified(Node *fmin) const {
        return haveincumbent &&
            static_cast<double>(incumbent) <=
                weight * static_cast<double>(fmin->g + fmin->h);
    }

    bool expand_cleanup(D &d) {
        Node *n = popf();
        if (!n)
            return false;
        expand(d, n);
        return !this->limit();
    }

    // One Triangle turn: serve at most one h-best node per layer, through
    // max-active-depth + slope.  Depths are absolute, so A* expansions made
    // before the switch remain naturally available to Triangle.
    bool triangle_cascade(D &d) {
        int maxactive = -1;
        for (int i = static_cast<int>(layers.size()) - 1; i >= 0; --i) {
            while (!layers[i].empty() && stale(layers[i].top()))
                layers[i].pop();
            if (!layers[i].empty()) {
                maxactive = i;
                break;
            }
        }
        if (maxactive < 0)
            return false;
        int cap = maxactive + slope;
        bool expanded = false;
        for (int i = 0; i < cap && !this->limit(); ++i) {
            if (i >= static_cast<int>(layers.size()))
                break;
            Node *n = poptriangle(i);
            if (!n)
                continue;
            expanded = true;
            expand(d, n);
            Node *fmin = peekf();
            if (!fmin || certified(fmin) ||
                (phase == TRIANGLE_ONLY && haveincumbent))
                break;
        }
        return expanded;
    }

    void expand(D &d, Node *n) {
        State buf, &state = d.unpack(buf, n->state);
        // A* recognizes goals when they are selected, not when generated.
        // Use the same rule in every regime so the synchronized queues differ
        // only in which live node they select.
        if (d.isgoal(state)) {
            n->status = CLOSED;
            updateincumbent(d, n);
            return;
        }

        n->status = CLOSED;
        this->res.expd++;
        typename D::Operators ops(d, state);
        for (unsigned int i = 0; i < ops.size() && !this->limit(); ++i) {
            if (ops[i] == n->pop)
                continue;
            this->res.gend++;
            considerkid(d, n, state, ops[i]);
        }
    }

    void considerkid(D &d, Node *parent, State &state, Oper op) {
        typename D::Edge edge(d, state, op);
        Cost g = parent->g + edge.cost;
        if (haveincumbent && g >= incumbent)
            return;

        Node *kid = nodes->construct();
        d.pack(kid->state, edge.state);
        unsigned long hash = kid->state.hash(&d);
        Node *dup = static_cast<Node *>(closed.find(kid->state, hash));
        Node *target = kid;
        if (!dup) {
            kid->parent = parent;
            kid->op = op;
            kid->pop = edge.revop;
            kid->g = g;
            kid->h = d.h(edge.state);
            kid->depth = parent->depth + 1;
            kid->status = OPEN;
            closed.add(kid, hash);
        } else {
            this->res.dups++;
            nodes->destruct(kid);
            if (!reopen || g >= dup->g)
                return;
            if (dup->status == CLOSED)
                this->res.reopnd++;
            dup->parent = parent;
            dup->op = op;
            dup->pop = edge.revop;
            dup->g = g;
            dup->depth = parent->depth + 1;
            dup->status = OPEN;
            target = dup;
        }

        insert(target);
    }

    void updateincumbent(D &d, Node *goal) {
        if (haveincumbent && !(goal->g < incumbent))
            return;
        incumbent = goal->g;
        haveincumbent = true;
        solpath<D, Node>(d, goal, this->res);
        ++nincumbent;
        dfrow(stdout, "incumbent", "uuugg", nincumbent, this->res.expd,
            this->res.gend, static_cast<double>(incumbent),
            walltime() - this->res.wallstart);
    }

    void rowhdr() {
        dfrowhdr(stdout, "incumbent", 5, "num", "nodes expanded",
            "nodes generated", "solution cost", "wall time");
    }

    int slope;
    double weight;
    double exponent;
    bool reopen;
    Phase phase = ASTAR_ONLY;

    FQueue cleanup;
    std::deque<Layer> layers;
    ClosedList<Node, Node, D> closed;
    Pool<Node> *nodes;

    bool haveincumbent = false;
    bool proved_bound = false;
    Cost incumbent = Cost(0);
    unsigned long nincumbent = 0;
    unsigned long rr_cleanup_turns = 0;
    unsigned long rr_triangle_turns = 0;
    bool switched = false;
    unsigned long switch_expansions = 0;
    double switch_g = 0.0;
    double switch_f = 0.0;
};
