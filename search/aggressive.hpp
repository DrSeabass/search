// Copyright © 2026 the Search Authors under the MIT license. See AUTHORS.
//
// Optimistic ("Aggressive") Search.  Before the first incumbent it expands
// weighted-A* order.  Afterwards synchronized weighted and admissible-f queues
// select the aggressive head while its weighted key can still improve the
// incumbent, otherwise the cleanup head.  Search ends when C <= w * f_min.
#pragma once
#include "../search/search.hpp"
#include "../utils/pool.hpp"
#include <cmath>
#include <cstring>
#include <cstdlib>
#include <queue>
#include <vector>

void dfrowhdr(FILE *, const char *, unsigned int ncols, ...);
void dfrow(FILE *, const char *, const char *, ...);
void fatal(const char *, ...);

template <class D> struct AggressiveSearch : public SearchAlgorithm<D> {
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
        Node() : parent(NULL), status(OPEN) {}
        static ClosedEntry<Node, D> &closedentry(Node *n) { return n->closedent; }
        static PackedState &key(Node *n) { return n->state; }
    private:
        ClosedEntry<Node, D> closedent;
    };
    struct Entry {
        Node *node;
        Cost g;
        Entry() : node(NULL), g(0) {}
        Entry(Node *n) : node(n), g(n->g) {}
    };
    struct FCmp {
        bool operator()(const Entry &a, const Entry &b) const {
            Cost af = a.g + a.node->h, bf = b.g + b.node->h;
            return af != bf ? af > bf : a.g < b.g;
        }
    };
    struct AggCmp {
        bool operator()(const Entry &a, const Entry &b) const {
            double af = static_cast<double>(a.g) + aggressive_weight *
                static_cast<double>(a.node->h);
            double bf = static_cast<double>(b.g) + aggressive_weight *
                static_cast<double>(b.node->h);
            if (af != bf) return af > bf;
            Cost aplain = a.g + a.node->h, bplain = b.g + b.node->h;
            return aplain != bplain ? aplain > bplain : a.g < b.g;
        }
        static double aggressive_weight;
    };
    typedef std::priority_queue<Entry, std::vector<Entry>, FCmp> FQueue;
    typedef std::priority_queue<Entry, std::vector<Entry>, AggCmp> AggQueue;

    AggressiveSearch(int argc, const char *argv[]) :
        SearchAlgorithm<D>(argc, argv), closed(30000001), nodes(new Pool<Node>()) {
        weight = -1.0;
        alpha = 2.0;
        reopen = true;
        for (int i = 0; i < argc; ++i) {
            if (i < argc - 1 && strcmp(argv[i], "-w") == 0)
                weight = strtod(argv[++i], NULL);
            else if (i < argc - 1 && strcmp(argv[i], "-alpha") == 0)
                alpha = strtod(argv[++i], NULL);
            else if (strcmp(argv[i], "-noreopen") == 0)
                reopen = false;
        }
        if (!(weight >= 1.0) || !std::isfinite(weight))
            fatal("Must specify a finite suboptimality bound >=1 using -w");
        if (!(alpha > 0.0) || !std::isfinite(alpha))
            fatal("Must specify a finite optimism factor >0 using -alpha");
        aggressive_weight = 1.0 + alpha * (weight - 1.0);
        AggCmp::aggressive_weight = aggressive_weight;
    }
    ~AggressiveSearch() { delete nodes; }

    void search(D &d, State &s0) {
        rowhdr();
        this->start();
        closed.init(d);
        Node *root = nodes->construct();
        d.pack(root->state, s0);
        root->parent = NULL;
        root->op = root->pop = D::Nop;
        root->g = Cost(0);
        root->h = d.h(s0);
        root->status = OPEN;
        closed.add(root, root->state.hash(&d));
        insert(root);

        while (!this->limit()) {
            Node *fmin = peekf();
            if (!fmin || certified(fmin))
                break;
            Node *n;
            Node *ahead = peekaggressive();
            if (!haveincumbent || (ahead && aggressive_key(ahead) <
                                   static_cast<double>(incumbent)))
                n = popaggressive();
            else
                n = popf();
            if (!n)
                break;
            expand(d, n);
        }
        Node *fmin = peekf();
        proved_bound = haveincumbent && (!fmin || certified(fmin));
        this->finish();
    }

    void reset() {
        SearchAlgorithm<D>::reset();
        fqueue = FQueue(); aggressive = AggQueue(); closed.clear();
        delete nodes; nodes = new Pool<Node>();
        haveincumbent = proved_bound = false; nincumbent = 0;
    }
    void output(FILE *out) {
        SearchAlgorithm<D>::output(out);
        closed.prstats(out, "closed ");
        dfpair(out, "open list type", "%s", "synchronized weighted and f heaps");
        dfpair(out, "node size", "%u", sizeof(Node));
        dfpair(out, "weight", "%g", weight);
        dfpair(out, "optimism alpha", "%g", alpha);
        dfpair(out, "aggressive weight", "%g", aggressive_weight);
        dfpair(out, "reopen closed", "%s", reopen ? "true" : "false");
        dfpair(out, "proved within bound", "%s", proved_bound ? "yes" : "no");
    }

private:
    bool stale(const Entry &e) const {
        return e.node->status == CLOSED || e.g != e.node->g;
    }
    Node *peekf() {
        while (!fqueue.empty() && stale(fqueue.top())) fqueue.pop();
        return fqueue.empty() ? NULL : fqueue.top().node;
    }
    Node *peekaggressive() {
        while (!aggressive.empty() && stale(aggressive.top())) aggressive.pop();
        return aggressive.empty() ? NULL : aggressive.top().node;
    }
    Node *popf() { Node *n = peekf(); if (n) fqueue.pop(); return n; }
    Node *popaggressive() {
        Node *n = peekaggressive(); if (n) aggressive.pop(); return n;
    }
    void insert(Node *n) { Entry e(n); fqueue.push(e); aggressive.push(e); }
    double aggressive_key(Node *n) const {
        return static_cast<double>(n->g) + aggressive_weight *
            static_cast<double>(n->h);
    }
    bool certified(Node *fmin) const {
        return haveincumbent && static_cast<double>(incumbent) <= weight *
            static_cast<double>(fmin->g + fmin->h);
    }
    void expand(D &d, Node *n) {
        State buf, &state = d.unpack(buf, n->state);
        if (d.isgoal(state)) {
            n->status = CLOSED;
            updateincumbent(d, n);
            return;
        }
        n->status = CLOSED;
        this->res.expd++;
        typename D::Operators ops(d, state);
        for (unsigned int i = 0; i < ops.size() && !this->limit(); ++i) {
            if (ops[i] == n->pop) continue;
            this->res.gend++;
            considerkid(d, n, state, ops[i]);
        }
    }
    void considerkid(D &d, Node *parent, State &state, Oper op) {
        typename D::Edge edge(d, state, op);
        Cost g = parent->g + edge.cost;
        Node *kid = nodes->construct();
        d.pack(kid->state, edge.state);
        unsigned long hash = kid->state.hash(&d);
        Node *dup = static_cast<Node *>(closed.find(kid->state, hash));
        Node *target = kid;
        if (!dup) {
            kid->g = g; kid->h = d.h(edge.state);
            if (haveincumbent && static_cast<double>(kid->g + kid->h) >=
                                 static_cast<double>(incumbent)) {
                nodes->destruct(kid); return;
            }
            kid->parent = parent; kid->op = op; kid->pop = edge.revop;
            kid->status = OPEN; closed.add(kid, hash);
        } else {
            this->res.dups++; nodes->destruct(kid);
            if (!reopen || g >= dup->g) return;
            if (haveincumbent && static_cast<double>(g + dup->h) >=
                                 static_cast<double>(incumbent)) return;
            if (dup->status == CLOSED) this->res.reopnd++;
            dup->g = g; dup->parent = parent; dup->op = op;
            dup->pop = edge.revop; dup->status = OPEN; target = dup;
        }
        insert(target);
    }
    void updateincumbent(D &d, Node *goal) {
        if (haveincumbent && !(goal->g < incumbent)) return;
        incumbent = goal->g; haveincumbent = true;
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

    double weight, alpha, aggressive_weight;
    bool reopen;
    FQueue fqueue;
    AggQueue aggressive;
    ClosedList<Node, Node, D> closed;
    Pool<Node> *nodes;
    bool haveincumbent = false, proved_bound = false;
    Cost incumbent = Cost(0);
    unsigned long nincumbent = 0;
};

template <class D>
double AggressiveSearch<D>::AggCmp::aggressive_weight = 1.0;

