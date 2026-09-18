/* warband._native: the grid searches of warband/path.py and the flag-grid painting of vision and
   of the workers' route map, in C, for the compiled simulation.

   warband/fastsim.py builds this module next to the mypyc-compiled modules; path.py hands its
   searches to it when it is there, which is only in the compiled simulation.  Every function
   computes exactly what its namesake in path.py computes: the same floating-point operations in
   the same order (the build turns floating-point contraction off, so no a + b * c becomes one
   fused instruction that rounds once), neighbours relaxed in the same order, the frontier popped
   in the same order.  heapq pops the least of tuples that never repeat, so any heap that pops the
   least gives the same sequence.  path.py is the reference: a change is made there first and
   then here, and tests/warband/test_fastsim.py holds the two to the same answers on random grids. */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

#ifdef __clang__
#pragma clang fp contract(off)
#endif

static double SQRT2, DIAGONAL; /* math.sqrt(2) and SQRT2 - 2, as path.py has them */

/* -- Arguments --------------------------------------------------------------------------------- */

/* The functions called many times a step take their arguments as METH_FASTCALL does, since
   PyArg_ParseTuple costs more than some of them do. */
static int check_count(const char *name, Py_ssize_t nargs, Py_ssize_t want) {
    if (nargs == want) return 0;
    PyErr_Format(PyExc_TypeError, "%s takes %zd arguments (%zd given)", name, want, nargs);
    return -1;
}

static int ssize_args(PyObject *const *args, Py_ssize_t count, Py_ssize_t *out) {
    for (Py_ssize_t i = 0; i < count; i++) {
        out[i] = PyLong_AsSsize_t(args[i]);
        if (out[i] == -1 && PyErr_Occurred()) return -1;
    }
    return 0;
}

/* -- The blocked grid -------------------------------------------------------------------------- */

typedef struct {
    Py_buffer view;
    const unsigned char *cells;
} Grid;

static int grid_open(PyObject *object, Py_ssize_t size, Grid *grid) {
    if (PyObject_GetBuffer(object, &grid->view, PyBUF_SIMPLE) < 0)
        return -1;
    if (grid->view.len < size) {
        PyBuffer_Release(&grid->view);
        PyErr_SetString(PyExc_ValueError, "the blocked grid is smaller than width * height");
        return -1;
    }
    grid->cells = (const unsigned char *)grid->view.buf;
    return 0;
}

static void grid_close(Grid *grid) { PyBuffer_Release(&grid->view); }

/* The walkable neighbours of a tile, in the order path.step_offsets lists them: east, west,
   south, north, then south-east, north-east, south-west, north-west.  A diagonal needs both
   orthogonals beside it open; its own tile is left for the caller to test. */
typedef struct {
    Py_ssize_t orthogonal[4];
    int orthogonals;
    Py_ssize_t diagonal[4];
    int diagonals;
} Steps;

static void steps_from(Py_ssize_t current, Py_ssize_t width, Py_ssize_t size, const unsigned char *blocked, Steps *steps) {
    Py_ssize_t x = current % width, below = current + width, above = current - width;
    int east = x + 1 < width && !blocked[current + 1];
    int west = x > 0 && !blocked[current - 1];
    int south = below < size && !blocked[below];
    int north = above >= 0 && !blocked[above];
    int n = 0;
    if (east) steps->orthogonal[n++] = 1;
    if (west) steps->orthogonal[n++] = -1;
    if (south) steps->orthogonal[n++] = width;
    if (north) steps->orthogonal[n++] = -width;
    steps->orthogonals = n;
    n = 0;
    if (east && south) steps->diagonal[n++] = width + 1;
    if (east && north) steps->diagonal[n++] = 1 - width;
    if (west && south) steps->diagonal[n++] = width - 1;
    if (west && north) steps->diagonal[n++] = -width - 1;
    steps->diagonals = n;
}

/* -- Heaps ------------------------------------------------------------------------------------- */

typedef struct { double f, g; Py_ssize_t index; } Node3; /* find_path_grid's (f, g, index) */
typedef struct { double cost; Py_ssize_t index; } Node2; /* (cost, index) */

typedef struct { Node3 *items; Py_ssize_t count, capacity; } Heap3;
typedef struct { Node2 *items; Py_ssize_t count, capacity; } Heap2;

static int less3(const Node3 *a, const Node3 *b) {
    if (a->f != b->f) return a->f < b->f;
    if (a->g != b->g) return a->g < b->g;
    return a->index < b->index;
}

static int less2(const Node2 *a, const Node2 *b) {
    if (a->cost != b->cost) return a->cost < b->cost;
    return a->index < b->index;
}

static int push3(Heap3 *heap, Node3 node) {
    if (heap->count == heap->capacity) {
        Py_ssize_t capacity = heap->capacity ? 2 * heap->capacity : 256;
        Node3 *items = PyMem_Realloc(heap->items, (size_t)capacity * sizeof(Node3));
        if (items == NULL) { PyErr_NoMemory(); return -1; }
        heap->items = items;
        heap->capacity = capacity;
    }
    Py_ssize_t pos = heap->count++;
    while (pos > 0) {
        Py_ssize_t parent = (pos - 1) >> 1;
        if (!less3(&node, &heap->items[parent])) break;
        heap->items[pos] = heap->items[parent];
        pos = parent;
    }
    heap->items[pos] = node;
    return 0;
}

static Node3 pop3(Heap3 *heap) {
    Node3 top = heap->items[0], last = heap->items[--heap->count];
    Py_ssize_t pos = 0, count = heap->count;
    for (;;) {
        Py_ssize_t child = 2 * pos + 1;
        if (child >= count) break;
        if (child + 1 < count && less3(&heap->items[child + 1], &heap->items[child])) child++;
        if (!less3(&heap->items[child], &last)) break;
        heap->items[pos] = heap->items[child];
        pos = child;
    }
    if (count) heap->items[pos] = last;
    return top;
}

static int push2(Heap2 *heap, Node2 node) {
    if (heap->count == heap->capacity) {
        Py_ssize_t capacity = heap->capacity ? 2 * heap->capacity : 256;
        Node2 *items = PyMem_Realloc(heap->items, (size_t)capacity * sizeof(Node2));
        if (items == NULL) { PyErr_NoMemory(); return -1; }
        heap->items = items;
        heap->capacity = capacity;
    }
    Py_ssize_t pos = heap->count++;
    while (pos > 0) {
        Py_ssize_t parent = (pos - 1) >> 1;
        if (!less2(&node, &heap->items[parent])) break;
        heap->items[pos] = heap->items[parent];
        pos = parent;
    }
    heap->items[pos] = node;
    return 0;
}

static Node2 pop2(Heap2 *heap) {
    Node2 top = heap->items[0], last = heap->items[--heap->count];
    Py_ssize_t pos = 0, count = heap->count;
    for (;;) {
        Py_ssize_t child = 2 * pos + 1;
        if (child >= count) break;
        if (child + 1 < count && less2(&heap->items[child + 1], &heap->items[child])) child++;
        if (!less2(&heap->items[child], &last)) break;
        heap->items[pos] = heap->items[child];
        pos = child;
    }
    if (count) heap->items[pos] = last;
    return top;
}

/* -- Helpers ----------------------------------------------------------------------------------- */

static int read_pos(PyObject *pos, Py_ssize_t *x, Py_ssize_t *y) {
    if (!PyTuple_Check(pos) || PyTuple_GET_SIZE(pos) != 2) {
        PyErr_SetString(PyExc_TypeError, "a tile is an (x, y) tuple");
        return -1;
    }
    *x = PyLong_AsSsize_t(PyTuple_GET_ITEM(pos, 0));
    if (*x == -1 && PyErr_Occurred()) return -1;
    *y = PyLong_AsSsize_t(PyTuple_GET_ITEM(pos, 1));
    if (*y == -1 && PyErr_Occurred()) return -1;
    return 0;
}

/* The tiles from the one after *origin* to *node*, as path.py's parent walk returns them. */
static PyObject *route_to(Py_ssize_t node, Py_ssize_t origin, const Py_ssize_t *parent, Py_ssize_t width) {
    Py_ssize_t length = 0;
    for (Py_ssize_t at = node; at != origin; at = parent[at]) length++;
    PyObject *route = PyList_New(length);
    if (route == NULL) return NULL;
    for (Py_ssize_t at = node, i = length - 1; at != origin; at = parent[at], i--) {
        PyObject *tile = Py_BuildValue("(nn)", at % width, at / width);
        if (tile == NULL) { Py_DECREF(route); return NULL; }
        PyList_SET_ITEM(route, i, tile);
    }
    return route;
}

static double octile_left(Py_ssize_t index, Py_ssize_t width, Py_ssize_t gx, Py_ssize_t gy) {
    Py_ssize_t nx = index % width, ny = index / width;
    Py_ssize_t dx = nx > gx ? nx - gx : gx - nx, dy = ny > gy ? ny - gy : gy - ny;
    double straight = (double)(dx + dy);
    double saved = DIAGONAL * (double)(dx > dy ? dy : dx);
    return straight + saved;
}

/* -- find_path_grid ---------------------------------------------------------------------------- */

static PyObject *find_path_grid(PyObject *self, PyObject *const *args, Py_ssize_t nargs) {
    Py_ssize_t v[3];
    if (check_count("find_path_grid", nargs, 6) < 0 || ssize_args(args + 3, 3, v) < 0) return NULL;
    PyObject *start_obj = args[0], *goal_obj = args[1], *blocked_obj = args[2];
    Py_ssize_t width = v[0], height = v[1], max_expansions = v[2];
    Py_ssize_t sx, sy, gx, gy;
    if (read_pos(start_obj, &sx, &sy) < 0 || read_pos(goal_obj, &gx, &gy) < 0) return NULL;
    if (sx == gx && sy == gy) return PyList_New(0);
    Py_ssize_t size = width * height, origin = sy * width + sx;
    if (origin < 0 || origin >= size) { PyErr_SetString(PyExc_ValueError, "the start is off the grid"); return NULL; }
    Grid grid;
    if (grid_open(blocked_obj, size, &grid) < 0) return NULL;
    const unsigned char *blocked = grid.cells;
    double *g_score = PyMem_Malloc((size_t)size * sizeof(double));
    Py_ssize_t *parent = PyMem_Malloc((size_t)size * sizeof(Py_ssize_t));
    unsigned char *done = PyMem_Calloc((size_t)size, 1);
    Heap3 frontier = {NULL, 0, 0};
    PyObject *result = NULL;
    if (g_score == NULL || parent == NULL || done == NULL) { PyErr_NoMemory(); goto out; }
    for (Py_ssize_t i = 0; i < size; i++) { g_score[i] = INFINITY; parent[i] = -1; }
    g_score[origin] = 0.0;
    Py_ssize_t dx = sx > gx ? sx - gx : gx - sx, dy = sy > gy ? sy - gy : gy - sy;
    Py_ssize_t best = origin;
    double best_h = (double)(dx + dy) + DIAGONAL * (double)(dx > dy ? dy : dx);
    if (push3(&frontier, (Node3){best_h, 0.0, origin}) < 0) goto out;
    Py_ssize_t expansions = 0;
    Steps steps;
    while (frontier.count && expansions < max_expansions) {
        Node3 top = pop3(&frontier);
        Py_ssize_t current = top.index;
        if (done[current]) continue;
        done[current] = 1;
        expansions++;
        if (current % width == gx && current / width == gy) { best = current; break; }
        steps_from(current, width, size, blocked, &steps);
        double ng = top.g + 1.0;
        for (int i = 0; i < steps.orthogonals; i++) {
            Py_ssize_t next = current + steps.orthogonal[i];
            if (ng < g_score[next]) {
                g_score[next] = ng;
                parent[next] = current;
                double h = octile_left(next, width, gx, gy);
                if (h < best_h || (h == best_h && ng < g_score[best])) { best = next; best_h = h; }
                double f = ng + h;
                if (push3(&frontier, (Node3){f, ng, next}) < 0) goto out;
            }
        }
        ng = top.g + SQRT2;
        for (int i = 0; i < steps.diagonals; i++) {
            Py_ssize_t next = current + steps.diagonal[i];
            if (blocked[next]) continue;
            if (ng < g_score[next]) {
                g_score[next] = ng;
                parent[next] = current;
                double h = octile_left(next, width, gx, gy);
                if (h < best_h || (h == best_h && ng < g_score[best])) { best = next; best_h = h; }
                double f = ng + h;
                if (push3(&frontier, (Node3){f, ng, next}) < 0) goto out;
            }
        }
    }
    result = route_to(best, origin, parent, width);
out:
    PyMem_Free(frontier.items);
    PyMem_Free(g_score);
    PyMem_Free(parent);
    PyMem_Free(done);
    grid_close(&grid);
    return result;
}

/* -- find_work_path ---------------------------------------------------------------------------- */

/* The cheapest goal to walk to from *origin*, each goal's penalty added to the walk: path.find_work_path's
   search.  Its index goes to *best* (-1 when no goal can be reached) and *parents* holds the walk to it. */
static int work_search(Py_ssize_t origin, const unsigned char *is_goal, const double *penalty, const unsigned char *blocked,
                       Py_ssize_t width, Py_ssize_t size, Py_ssize_t *parents, Py_ssize_t *best_out) {
    double *costs = PyMem_Malloc((size_t)size * sizeof(double));
    Heap2 frontier = {NULL, 0, 0};
    int status = -1;
    if (costs == NULL) { PyErr_NoMemory(); goto out; }
    for (Py_ssize_t i = 0; i < size; i++) { costs[i] = INFINITY; parents[i] = -1; }
    costs[origin] = 0.0;
    if (push2(&frontier, (Node2){0.0, origin}) < 0) goto out;
    Py_ssize_t best = -1;
    double best_cost = INFINITY;
    Steps steps;
    while (frontier.count) {
        Node2 top = pop2(&frontier);
        double cost = top.cost;
        Py_ssize_t current = top.index;
        if (cost >= best_cost) break;
        if (cost != costs[current]) continue;
        if (is_goal[current]) {
            double total = cost + penalty[current];
            if (total < best_cost) { best = current; best_cost = total; }
        }
        steps_from(current, width, size, blocked, &steps);
        double total = cost + 1.0;
        for (int i = 0; i < steps.orthogonals; i++) {
            Py_ssize_t next = current + steps.orthogonal[i];
            if (total < costs[next]) {
                costs[next] = total;
                parents[next] = current;
                if (push2(&frontier, (Node2){total, next}) < 0) goto out;
            }
        }
        total = cost + SQRT2;
        for (int i = 0; i < steps.diagonals; i++) {
            Py_ssize_t next = current + steps.diagonal[i];
            if (!blocked[next] && total < costs[next]) {
                costs[next] = total;
                parents[next] = current;
                if (push2(&frontier, (Node2){total, next}) < 0) goto out;
            }
        }
    }
    *best_out = best;
    status = 0;
out:
    PyMem_Free(frontier.items);
    PyMem_Free(costs);
    return status;
}

static PyObject *find_work_path(PyObject *self, PyObject *const *args, Py_ssize_t nargs) {
    Py_ssize_t v[2];
    if (check_count("find_work_path", nargs, 5) < 0 || ssize_args(args + 3, 2, v) < 0) return NULL;
    PyObject *start_obj = args[0], *goals = args[1], *blocked_obj = args[2];
    Py_ssize_t width = v[0], height = v[1];
    if (!PyDict_Check(goals)) { PyErr_SetString(PyExc_TypeError, "the goals are a dict"); return NULL; }
    if (PyDict_GET_SIZE(goals) == 0) Py_RETURN_NONE;
    Py_ssize_t sx, sy;
    if (read_pos(start_obj, &sx, &sy) < 0) return NULL;
    Py_ssize_t size = width * height, origin = sy * width + sx;
    if (origin < 0 || origin >= size) { PyErr_SetString(PyExc_ValueError, "the start is off the grid"); return NULL; }
    Grid grid;
    if (grid_open(blocked_obj, size, &grid) < 0) return NULL;
    double *penalty = PyMem_Malloc((size_t)size * sizeof(double));
    unsigned char *is_goal = PyMem_Calloc((size_t)size, 1);
    Py_ssize_t *parents = PyMem_Malloc((size_t)size * sizeof(Py_ssize_t));
    PyObject *result = NULL;
    if (penalty == NULL || is_goal == NULL || parents == NULL) { PyErr_NoMemory(); goto out; }
    /* {y * width + x: penalty for (x, y), penalty in goals.items()}: later keys that land on the
       same index replace earlier ones, and an index off the grid is never reached. */
    Py_ssize_t position = 0;
    PyObject *key, *value;
    while (PyDict_Next(goals, &position, &key, &value)) {
        Py_ssize_t x, y;
        if (read_pos(key, &x, &y) < 0) goto out;
        double amount = PyFloat_AsDouble(value);
        if (amount == -1.0 && PyErr_Occurred()) goto out;
        Py_ssize_t index = y * width + x;
        if (index >= 0 && index < size) { penalty[index] = amount; is_goal[index] = 1; }
    }
    Py_ssize_t best;
    if (work_search(origin, is_goal, penalty, grid.cells, width, size, parents, &best) < 0) goto out;
    if (best < 0) {
        Py_INCREF(Py_None);
        result = Py_None;
    } else {
        result = route_to(best, origin, parents, width);
    }
out:
    PyMem_Free(penalty);
    PyMem_Free(is_goal);
    PyMem_Free(parents);
    grid_close(&grid);
    return result;
}

/* -- choose_tree ------------------------------------------------------------------------------- */

/* worker_ai._choose_tree: every remembered tree nobody is felling offers the open tiles around it
   (the offsets of *reach*, in order) at twice their walk to a depot, a tile going to the cheaper tree
   and to the one nearer the top left on a tie; the worker at *start* takes the claim it can reach
   most cheaply, and the answer is that tree, or None. */
static PyObject *choose_tree(PyObject *self, PyObject *args) {
    PyObject *start_obj, *trees_obj, *loaded, *remembered, *marker, *field_obj, *blocked_obj, *reach_obj;
    Py_ssize_t width, height;
    if (!PyArg_ParseTuple(args, "OOOO!OOOOnn", &start_obj, &trees_obj, &loaded, &PyList_Type, &remembered, &marker,
                          &field_obj, &blocked_obj, &reach_obj, &width, &height))
        return NULL;
    Py_ssize_t sx, sy;
    if (read_pos(start_obj, &sx, &sy) < 0) return NULL;
    Py_ssize_t size = width * height, origin = sy * width + sx;
    if (origin < 0 || origin >= size) { PyErr_SetString(PyExc_ValueError, "the start is off the grid"); return NULL; }
    if (PyList_GET_SIZE(remembered) < size) { PyErr_SetString(PyExc_ValueError, "the remembered terrain is too short"); return NULL; }
    PyObject *trees = PySequence_Fast(trees_obj, "the trees are a sequence of flat indices");
    if (trees == NULL) return NULL;
    PyObject *reach = PySequence_Fast(reach_obj, "reach is a sequence of (dx, dy)");
    if (reach == NULL) { Py_DECREF(trees); return NULL; }
    Grid grid, field;
    if (grid_open(blocked_obj, size, &grid) < 0) { Py_DECREF(trees); Py_DECREF(reach); return NULL; }
    if (PyObject_GetBuffer(field_obj, &field.view, PyBUF_FORMAT) < 0) {
        grid_close(&grid); Py_DECREF(trees); Py_DECREF(reach); return NULL;
    }
    PyObject *result = NULL;
    unsigned char *taken = NULL, *is_goal = NULL;
    double *cost = NULL;
    Py_ssize_t *owner = NULL, *parents = NULL, *offsets = NULL;
    if (field.view.itemsize != sizeof(double) || field.view.len < size * (Py_ssize_t)sizeof(double)) {
        PyErr_SetString(PyExc_ValueError, "the depot field is an array('d') of width * height");
        goto out;
    }
    const double *distance = (const double *)field.view.buf;
    const unsigned char *blocked = grid.cells;
    Py_ssize_t reaches = PySequence_Fast_GET_SIZE(reach);
    taken = PyMem_Calloc((size_t)size, 1);
    is_goal = PyMem_Calloc((size_t)size, 1);
    cost = PyMem_Malloc((size_t)size * sizeof(double));
    owner = PyMem_Malloc((size_t)size * sizeof(Py_ssize_t));
    parents = PyMem_Malloc((size_t)size * sizeof(Py_ssize_t));
    offsets = PyMem_Malloc((size_t)(2 * reaches + 1) * sizeof(Py_ssize_t));
    if (taken == NULL || is_goal == NULL || cost == NULL || owner == NULL || parents == NULL || offsets == NULL) {
        PyErr_NoMemory();
        goto out;
    }
    for (Py_ssize_t i = 0; i < reaches; i++)
        if (read_pos(PySequence_Fast_GET_ITEM(reach, i), &offsets[2 * i], &offsets[2 * i + 1]) < 0) goto out;
    PyObject *iterator = PyObject_GetIter(loaded), *item;
    if (iterator == NULL) goto out;
    while ((item = PyIter_Next(iterator)) != NULL) {
        Py_ssize_t index = PyLong_AsSsize_t(item);
        Py_DECREF(item);
        if (index == -1 && PyErr_Occurred()) { Py_DECREF(iterator); goto out; }
        if (index >= 0 && index < size) taken[index] = 1;
    }
    Py_DECREF(iterator);
    if (PyErr_Occurred()) goto out;
    int any = 0;
    Py_ssize_t count = PySequence_Fast_GET_SIZE(trees);
    for (Py_ssize_t i = 0; i < count; i++) {
        Py_ssize_t tree = PyLong_AsSsize_t(PySequence_Fast_GET_ITEM(trees, i));
        if (tree == -1 && PyErr_Occurred()) goto out;
        if (tree < 0 || tree >= size) { PyErr_SetString(PyExc_ValueError, "a tree is off the grid"); goto out; }
        if (taken[tree] || PyList_GET_ITEM(remembered, tree) != marker) continue;
        Py_ssize_t x = tree % width, y = tree / width;
        for (Py_ssize_t r = 0; r < reaches; r++) {
            Py_ssize_t tx = x + offsets[2 * r], ty = y + offsets[2 * r + 1];
            if (tx < 0 || tx >= width || ty < 0 || ty >= height) continue;
            Py_ssize_t tile = ty * width + tx;
            if (blocked[tile]) continue;
            double walk = distance[tile];
            if (!(walk < INFINITY)) continue;
            double claim = 2.0 * walk;
            if (!is_goal[tile] || claim < cost[tile]
                    || (claim == cost[tile] && (x < owner[tile] % width
                                                || (x == owner[tile] % width && y < owner[tile] / width)))) {
                is_goal[tile] = 1;
                cost[tile] = claim;
                owner[tile] = tree;
            }
            any = 1;
        }
    }
    if (!any) { Py_INCREF(Py_None); result = Py_None; goto out; }
    Py_ssize_t best;
    if (work_search(origin, is_goal, cost, blocked, width, size, parents, &best) < 0) goto out;
    if (best < 0) {
        Py_INCREF(Py_None);
        result = Py_None;
    } else {
        result = Py_BuildValue("(nn)", owner[best] % width, owner[best] / width);
    }
out:
    PyMem_Free(taken);
    PyMem_Free(is_goal);
    PyMem_Free(cost);
    PyMem_Free(owner);
    PyMem_Free(parents);
    PyMem_Free(offsets);
    PyBuffer_Release(&field.view);
    grid_close(&grid);
    Py_DECREF(trees);
    Py_DECREF(reach);
    return result;
}

/* -- distance_field ---------------------------------------------------------------------------- */

static int compare_indices(const void *a, const void *b) {
    Py_ssize_t x = *(const Py_ssize_t *)a, y = *(const Py_ssize_t *)b;
    return (x > y) - (x < y);
}

static PyObject *distance_field(PyObject *self, PyObject *args) {
    PyObject *starts_obj, *blocked_obj, *out_obj;
    Py_ssize_t width, height;
    if (!PyArg_ParseTuple(args, "OOnnO", &starts_obj, &blocked_obj, &width, &height, &out_obj))
        return NULL;
    Py_ssize_t size = width * height;
    Py_buffer out_view;
    if (PyObject_GetBuffer(out_obj, &out_view, PyBUF_WRITABLE | PyBUF_FORMAT) < 0) return NULL;
    if (out_view.itemsize != sizeof(double) || out_view.len < size * (Py_ssize_t)sizeof(double)) {
        PyBuffer_Release(&out_view);
        PyErr_SetString(PyExc_ValueError, "the field is an array('d') of width * height");
        return NULL;
    }
    PyObject *starts = PySequence_Fast(starts_obj, "the starts are a sequence of flat indices");
    if (starts == NULL) { PyBuffer_Release(&out_view); return NULL; }
    Py_ssize_t count = PySequence_Fast_GET_SIZE(starts);
    Grid grid;
    if (grid_open(blocked_obj, size, &grid) < 0) { Py_DECREF(starts); PyBuffer_Release(&out_view); return NULL; }
    const unsigned char *blocked = grid.cells;
    double *distances = (double *)out_view.buf;
    Py_ssize_t *sorted = PyMem_Malloc((size_t)(count ? count : 1) * sizeof(Py_ssize_t));
    Heap2 frontier = {NULL, 0, 0};
    PyObject *result = NULL;
    if (sorted == NULL) { PyErr_NoMemory(); goto out; }
    for (Py_ssize_t i = 0; i < count; i++) {
        sorted[i] = PyLong_AsSsize_t(PySequence_Fast_GET_ITEM(starts, i));
        if (sorted[i] == -1 && PyErr_Occurred()) goto out;
        if (sorted[i] < 0 || sorted[i] >= size) { PyErr_SetString(PyExc_ValueError, "a start is off the grid"); goto out; }
    }
    qsort(sorted, (size_t)count, sizeof(Py_ssize_t), compare_indices);
    for (Py_ssize_t i = 0; i < size; i++) distances[i] = INFINITY;
    for (Py_ssize_t i = 0; i < count; i++) {
        distances[sorted[i]] = 0.0;
        if (push2(&frontier, (Node2){0.0, sorted[i]}) < 0) goto out;
    }
    Steps steps;
    while (frontier.count) {
        Node2 top = pop2(&frontier);
        double cost = top.cost;
        Py_ssize_t current = top.index;
        if (cost > distances[current]) continue;
        steps_from(current, width, size, blocked, &steps);
        double total = cost + 1.0;
        for (int i = 0; i < steps.orthogonals; i++) {
            Py_ssize_t next = current + steps.orthogonal[i];
            if (total < distances[next]) {
                distances[next] = total;
                if (push2(&frontier, (Node2){total, next}) < 0) goto out;
            }
        }
        total = cost + SQRT2;
        for (int i = 0; i < steps.diagonals; i++) {
            Py_ssize_t next = current + steps.diagonal[i];
            if (!blocked[next] && total < distances[next]) {
                distances[next] = total;
                if (push2(&frontier, (Node2){total, next}) < 0) goto out;
            }
        }
    }
    Py_INCREF(Py_None);
    result = Py_None;
out:
    PyMem_Free(frontier.items);
    PyMem_Free(sorted);
    grid_close(&grid);
    Py_DECREF(starts);
    PyBuffer_Release(&out_view);
    return result;
}

/* -- Regions ----------------------------------------------------------------------------------- */

/* Label the walkable regions into *labels* (a writable buffer of C ints, width * height long) as
   Regions.__init__ does: regions numbered from 1 in the order of their first tile, blocked tiles 0. */
static PyObject *region_labels(PyObject *self, PyObject *args) {
    PyObject *blocked_obj, *labels_obj;
    Py_ssize_t width, height;
    if (!PyArg_ParseTuple(args, "OnnO", &blocked_obj, &width, &height, &labels_obj))
        return NULL;
    Py_ssize_t size = width * height;
    Grid grid;
    if (grid_open(blocked_obj, size, &grid) < 0) return NULL;
    Py_buffer view;
    if (PyObject_GetBuffer(labels_obj, &view, PyBUF_WRITABLE | PyBUF_FORMAT) < 0) { grid_close(&grid); return NULL; }
    PyObject *result = NULL;
    Py_ssize_t *stack = NULL;
    if (view.itemsize != sizeof(int) || view.len < size * (Py_ssize_t)sizeof(int)) {
        PyErr_SetString(PyExc_ValueError, "the labels are an array('i') of width * height");
        goto out;
    }
    int *labels = (int *)view.buf;
    const unsigned char *blocked = grid.cells;
    stack = PyMem_Malloc((size_t)size * sizeof(Py_ssize_t));
    if (stack == NULL) { PyErr_NoMemory(); goto out; }
    memset(labels, 0, (size_t)size * sizeof(int));
    int region = 0;
    for (Py_ssize_t seed = 0; seed < size; seed++) {
        if (blocked[seed] || labels[seed]) continue;
        region++;
        labels[seed] = region;
        Py_ssize_t depth = 0;
        stack[depth++] = seed;
        while (depth) {
            Py_ssize_t index = stack[--depth];
            Py_ssize_t x = index % width;
            Py_ssize_t around[4] = {index - width, index + width, x ? index - 1 : -1, x + 1 < width ? index + 1 : -1};
            for (int i = 0; i < 4; i++) {
                Py_ssize_t next = around[i];
                if (next >= 0 && next < size && !blocked[next] && !labels[next]) {
                    labels[next] = region;
                    stack[depth++] = next;
                }
            }
        }
    }
    result = PyLong_FromLong(region);
out:
    PyMem_Free(stack);
    PyBuffer_Release(&view);
    grid_close(&grid);
    return result;
}

/* Regions.reachable_goal's scan: the tile of *region* nearest *goal* by octile distance, the
   first in row-major order among equals; *goal* itself when the region has no tile. */
static PyObject *nearest_in_region(PyObject *self, PyObject *args) {
    PyObject *labels_obj, *goal_obj;
    long region;
    Py_ssize_t width;
    if (!PyArg_ParseTuple(args, "OlOn", &labels_obj, &region, &goal_obj, &width))
        return NULL;
    Py_ssize_t gx, gy;
    if (read_pos(goal_obj, &gx, &gy) < 0) return NULL;
    Py_buffer view;
    if (PyObject_GetBuffer(labels_obj, &view, PyBUF_FORMAT) < 0) return NULL;
    if (view.itemsize != sizeof(int)) {
        PyBuffer_Release(&view);
        PyErr_SetString(PyExc_ValueError, "the labels are an array('i')");
        return NULL;
    }
    const int *labels = (const int *)view.buf;
    Py_ssize_t count = view.len / (Py_ssize_t)sizeof(int), best = -1;
    double best_h = INFINITY;
    for (Py_ssize_t index = 0; index < count; index++) {
        if (labels[index] != region) continue;
        double h = octile_left(index, width, gx, gy);
        if (h < best_h) { best = index; best_h = h; }
    }
    PyBuffer_Release(&view);
    if (best < 0) {
        Py_INCREF(goal_obj);
        return goal_obj;
    }
    return Py_BuildValue("(nn)", best % width, best / width);
}

/* -- Painting on flag grids -------------------------------------------------------------------- */

static int open_writable(PyObject *object, Py_ssize_t size, Py_buffer *view) {
    if (PyObject_GetBuffer(object, view, PyBUF_WRITABLE) < 0) return -1;
    if (view->len < size) {
        PyBuffer_Release(view);
        PyErr_SetString(PyExc_ValueError, "the grid is smaller than width * height");
        return -1;
    }
    return 0;
}

static Py_ssize_t isqrt_of(Py_ssize_t value) {  /* math.isqrt for the small values sight needs */
    Py_ssize_t root = (Py_ssize_t)sqrt((double)value);
    while (root * root > value) root--;
    while ((root + 1) * (root + 1) <= value) root++;
    return root;
}

/* model.World._reveal for every ((x, y), radius) of *discs*: each row of a sight disc reaches
   isqrt(r * r + r - dy * dy) tiles sideways, and rows and runs are clipped to the map. */
static PyObject *stamp_discs(PyObject *self, PyObject *const *args, Py_ssize_t nargs) {
    Py_ssize_t v[2];
    if (check_count("stamp_discs", nargs, 4) < 0 || ssize_args(args + 2, 2, v) < 0) return NULL;
    PyObject *visible_obj = args[0], *discs = args[1];
    Py_ssize_t width = v[0], height = v[1];
    Py_buffer view;
    if (open_writable(visible_obj, width * height, &view) < 0) return NULL;
    unsigned char *visible = (unsigned char *)view.buf;
    PyObject *iterator = PyObject_GetIter(discs), *disc;
    if (iterator == NULL) { PyBuffer_Release(&view); return NULL; }
    while ((disc = PyIter_Next(iterator)) != NULL) {
        PyObject *at;
        Py_ssize_t x0, y0, radius;
        int ok = PyTuple_Check(disc) && PyTuple_GET_SIZE(disc) == 2;
        if (ok) {
            at = PyTuple_GET_ITEM(disc, 0);
            radius = PyLong_AsSsize_t(PyTuple_GET_ITEM(disc, 1));
            ok = !(radius == -1 && PyErr_Occurred()) && read_pos(at, &x0, &y0) == 0;
        } else {
            PyErr_SetString(PyExc_TypeError, "a disc is ((x, y), radius)");
        }
        Py_DECREF(disc);
        if (!ok) { Py_DECREF(iterator); PyBuffer_Release(&view); return NULL; }
        for (Py_ssize_t dy = -radius; dy <= radius; dy++) {
            Py_ssize_t y = y0 + dy;
            if (y < 0 || y >= height) continue;
            Py_ssize_t half = isqrt_of(radius * radius + radius - dy * dy);
            Py_ssize_t lo = x0 - half, hi = x0 + half + 1;
            if (lo < 0) lo = 0;
            if (hi > width) hi = width;
            if (lo < hi) memset(visible + y * width + lo, 1, (size_t)(hi - lo));
        }
    }
    Py_DECREF(iterator);
    PyBuffer_Release(&view);
    if (PyErr_Occurred()) return NULL;
    Py_RETURN_NONE;
}

/* model.or_into: target[i] |= source[i] for every byte. */
static PyObject *or_into(PyObject *self, PyObject *const *args, Py_ssize_t nargs) {
    if (check_count("or_into", nargs, 2) < 0) return NULL;
    PyObject *target_obj = args[0], *source_obj = args[1];
    Py_buffer target, source;
    if (PyObject_GetBuffer(target_obj, &target, PyBUF_WRITABLE) < 0) return NULL;
    if (PyObject_GetBuffer(source_obj, &source, PyBUF_SIMPLE) < 0) { PyBuffer_Release(&target); return NULL; }
    if (source.len != target.len) {
        PyBuffer_Release(&target);
        PyBuffer_Release(&source);
        PyErr_SetString(PyExc_ValueError, "or_into needs two grids of one size");
        return NULL;
    }
    unsigned char *to = (unsigned char *)target.buf;
    const unsigned char *from = (const unsigned char *)source.buf;
    for (Py_ssize_t i = 0; i < target.len; i++) to[i] |= from[i];
    PyBuffer_Release(&target);
    PyBuffer_Release(&source);
    Py_RETURN_NONE;
}

/* worker_ai._stamp_units: for each (x, y, radius), block the tiles whose centre lies within
   radius of the point, one run per row, with the same float steps as the Python. */
static PyObject *stamp_threats(PyObject *self, PyObject *const *args, Py_ssize_t nargs) {
    Py_ssize_t v[2];
    if (check_count("stamp_threats", nargs, 4) < 0 || ssize_args(args + 2, 2, v) < 0) return NULL;
    PyObject *blocked_obj = args[0], *units = args[1];
    Py_ssize_t width = v[0], height = v[1];
    Py_buffer view;
    if (open_writable(blocked_obj, width * height, &view) < 0) return NULL;
    unsigned char *blocked = (unsigned char *)view.buf;
    PyObject *iterator = PyObject_GetIter(units), *unit;
    if (iterator == NULL) { PyBuffer_Release(&view); return NULL; }
    while ((unit = PyIter_Next(iterator)) != NULL) {
        double values[3];
        int ok = PyTuple_Check(unit) && PyTuple_GET_SIZE(unit) == 3;
        for (int i = 0; ok && i < 3; i++) {
            values[i] = PyFloat_AsDouble(PyTuple_GET_ITEM(unit, i));
            ok = !(values[i] == -1.0 && PyErr_Occurred());
        }
        if (!ok && !PyErr_Occurred()) PyErr_SetString(PyExc_TypeError, "a threat is (x, y, radius)");
        Py_DECREF(unit);
        if (!ok) { Py_DECREF(iterator); PyBuffer_Release(&view); return NULL; }
        double cx = values[0], cy = values[1], radius = values[2];
        double r2 = radius * radius;
        double top = floor(cy - radius), bottom = ceil(cy + radius);
        Py_ssize_t first = top > 0.0 ? (Py_ssize_t)top : 0;
        Py_ssize_t last = (Py_ssize_t)bottom + 1;
        if (last > height) last = height;
        for (Py_ssize_t y = first; y < last; y++) {
            double dy = ((double)y + 0.5) - cy;
            double offset = dy * dy;
            if (offset > r2) continue;
            double half = sqrt(r2 - offset);
            double left = ceil((cx - half) - 0.5), right = floor((cx + half) - 0.5);
            Py_ssize_t lo = left > 0.0 ? (Py_ssize_t)left : 0;
            Py_ssize_t hi = (Py_ssize_t)right + 1;
            if (hi > width) hi = width;
            if (lo < hi) memset(blocked + y * width + lo, 1, (size_t)(hi - lo));
        }
    }
    Py_DECREF(iterator);
    PyBuffer_Release(&view);
    if (PyErr_Occurred()) return NULL;
    Py_RETURN_NONE;
}

/* World.any_visible and WorkerKnowledge.sees: whether any tile of the w by h rectangle at (x, y),
   clipped to the map, is lit in *visible*. */
static PyObject *any_lit(PyObject *self, PyObject *const *args, Py_ssize_t nargs) {
    Py_ssize_t v[6];
    if (check_count("any_lit", nargs, 7) < 0 || ssize_args(args + 1, 6, v) < 0) return NULL;
    PyObject *visible_obj = args[0];
    Py_ssize_t x = v[0], y = v[1], w = v[2], h = v[3], width = v[4], height = v[5];
    Grid grid;
    if (grid_open(visible_obj, width * height, &grid) < 0) return NULL;
    Py_ssize_t left = x > 0 ? x : 0, right = x + w < width ? x + w : width;
    Py_ssize_t top = y > 0 ? y : 0, bottom = y + h < height ? y + h : height;
    int lit = 0;
    for (Py_ssize_t row = top; row < bottom && !lit; row++)
        for (Py_ssize_t col = left; col < right; col++)
            if (grid.cells[row * width + col]) { lit = 1; break; }
    grid_close(&grid);
    return PyBool_FromLong(lit);
}

/* WorkerKnowledge._stale: the flat indices, in map order, of the lit tiles whose remembered terrain
   is not the terrain there now (compared by identity, as `is not` does). */
static PyObject *stale_tiles(PyObject *self, PyObject *const *args, Py_ssize_t nargs) {
    Py_ssize_t v[2];
    if (check_count("stale_tiles", nargs, 5) < 0 || ssize_args(args + 3, 2, v) < 0) return NULL;
    PyObject *visible_obj = args[0], *rows = args[1], *remembered = args[2];
    Py_ssize_t width = v[0], height = v[1];
    if (!PyList_Check(rows) || !PyList_Check(remembered)) {
        PyErr_SetString(PyExc_TypeError, "the terrain rows and the remembered terrain are lists");
        return NULL;
    }
    if (PyList_GET_SIZE(rows) < height || PyList_GET_SIZE(remembered) < width * height) {
        PyErr_SetString(PyExc_ValueError, "the terrain is smaller than width * height");
        return NULL;
    }
    Grid grid;
    if (grid_open(visible_obj, width * height, &grid) < 0) return NULL;
    PyObject *stale = PyList_New(0);
    for (Py_ssize_t y = 0; stale != NULL && y < height; y++) {
        PyObject *row = PyList_GET_ITEM(rows, y);
        if (!PyList_Check(row) || PyList_GET_SIZE(row) < width) {
            PyErr_SetString(PyExc_ValueError, "a terrain row is not a list of width tiles");
            Py_CLEAR(stale);
            break;
        }
        const unsigned char *lit = grid.cells + y * width;
        for (Py_ssize_t x = 0; x < width; x++) {
            if (!lit[x] || PyList_GET_ITEM(remembered, y * width + x) == PyList_GET_ITEM(row, x)) continue;
            PyObject *index = PyLong_FromSsize_t(y * width + x);
            if (index == NULL || PyList_Append(stale, index) < 0) {
                Py_XDECREF(index);
                Py_CLEAR(stale);
                break;
            }
            Py_DECREF(index);
        }
    }
    grid_close(&grid);
    return stale;
}

/* -- site_search ------------------------------------------------------------------------------ */

typedef struct { double score; Py_ssize_t x, y; } Candidate;

static int compare_candidates(const void *a, const void *b) {  /* as Python orders (score, (x, y)) */
    const Candidate *p = a, *q = b;
    if (p->score != q->score) return p->score < q->score ? -1 : 1;
    if (p->x != q->x) return p->x < q->x ? -1 : 1;
    return (p->y > q->y) - (p->y < q->y);
}

static int read_ints(PyObject *item, Py_ssize_t *out, Py_ssize_t count, const char *what) {
    if (!PyTuple_Check(item) || PyTuple_GET_SIZE(item) != count) { PyErr_Format(PyExc_TypeError, "%s", what); return -1; }
    for (Py_ssize_t i = 0; i < count; i++) {
        out[i] = PyLong_AsSsize_t(PyTuple_GET_ITEM(item, i));
        if (out[i] == -1 && PyErr_Occurred()) return -1;
    }
    return 0;
}

static Py_ssize_t max3(Py_ssize_t a, Py_ssize_t b, Py_ssize_t c) { Py_ssize_t m = a > b ? a : b; return m > c ? m : c; }

/* model.rects_gap: tiles of clearance between two tile rectangles (Chebyshev; 0 when they touch or overlap). */
static Py_ssize_t rects_gap(const Py_ssize_t *a, const Py_ssize_t *b) {
    Py_ssize_t dx = max3(b[0] - (a[0] + a[2]), a[0] - (b[0] + b[2]), 0);
    Py_ssize_t dy = max3(b[1] - (a[1] + a[3]), a[1] - (b[1] + b[3]), 0);
    return dx > dy ? dx : dy;
}

/* ai.site_search from the ring, the corner, rng.random and ai.site_inputs: every spot of the ring scored by
   its distance plus two random draws of a tile, drawn in ring order whether or not any spot can do; then
   the first in sorted order that no taken site crowds, whose ground is open grass the player has explored,
   with no unit standing on it, far enough from every gold mine, and a tile clear of every one of the
   player's buildings.  None when there is none. */
static PyObject *site_search(PyObject *self, PyObject *args) {
    PyObject *ring_obj, *draw, *taken_obj, *rows, *grass, *blocked_obj, *explored_obj, *standing_obj, *mines_obj, *own_obj;
    Py_ssize_t origin_x, origin_y, size, width, height, clearance;
    int possible;
    if (!PyArg_ParseTuple(args, "OnnOpnOO!OOOOOOnnn", &ring_obj, &origin_x, &origin_y, &draw, &possible, &size, &taken_obj,
                          &PyList_Type, &rows, &grass, &blocked_obj, &explored_obj, &standing_obj, &mines_obj, &own_obj,
                          &width, &height, &clearance))
        return NULL;
    if (PyList_GET_SIZE(rows) < height) { PyErr_SetString(PyExc_ValueError, "the terrain has too few rows"); return NULL; }
    PyObject *ring = NULL, *taken = NULL, *standing = NULL, *mines = NULL, *own = NULL, *result = NULL;
    Candidate *order = NULL;
    Py_ssize_t *taken_at = NULL, *mine_rects = NULL, *own_rects = NULL;
    double *units = NULL;
    Grid blocked, explored;
    int blocked_open = 0, explored_open = 0;
    if ((ring = PySequence_Fast(ring_obj, "the ring is a sequence of (distance, dx, dy)")) == NULL) goto out;
    if ((taken = PySequence_Fast(taken_obj, "taken is a sequence of ((x, y), size)")) == NULL) goto out;
    if ((standing = PySequence_Fast(standing_obj, "standing is a sequence of (x, y, radius)")) == NULL) goto out;
    if ((mines = PySequence_Fast(mines_obj, "mines is a sequence of rectangles")) == NULL) goto out;
    if ((own = PySequence_Fast(own_obj, "own is a sequence of rectangles")) == NULL) goto out;
    if (grid_open(blocked_obj, width * height, &blocked) < 0) goto out;
    blocked_open = 1;
    if (grid_open(explored_obj, width * height, &explored) < 0) goto out;
    explored_open = 1;
    Py_ssize_t count = PySequence_Fast_GET_SIZE(ring), ntaken = PySequence_Fast_GET_SIZE(taken);
    Py_ssize_t nunits = PySequence_Fast_GET_SIZE(standing), nmines = PySequence_Fast_GET_SIZE(mines), nown = PySequence_Fast_GET_SIZE(own);
    order = PyMem_Malloc((size_t)(count + 1) * sizeof(Candidate));
    taken_at = PyMem_Malloc((size_t)(3 * ntaken + 1) * sizeof(Py_ssize_t));
    units = PyMem_Malloc((size_t)(3 * nunits + 1) * sizeof(double));
    mine_rects = PyMem_Malloc((size_t)(4 * nmines + 1) * sizeof(Py_ssize_t));
    own_rects = PyMem_Malloc((size_t)(4 * nown + 1) * sizeof(Py_ssize_t));
    if (order == NULL || taken_at == NULL || units == NULL || mine_rects == NULL || own_rects == NULL) { PyErr_NoMemory(); goto out; }
    for (Py_ssize_t i = 0; i < count; i++) {  /* distance + rng.random() * 2, in ring order */
        PyObject *item = PySequence_Fast_GET_ITEM(ring, i);
        Py_ssize_t offset[2];
        if (!PyTuple_Check(item) || PyTuple_GET_SIZE(item) != 3) { PyErr_SetString(PyExc_TypeError, "a ring spot is (distance, dx, dy)"); goto out; }
        double distance = PyFloat_AsDouble(PyTuple_GET_ITEM(item, 0));
        if (distance == -1.0 && PyErr_Occurred()) goto out;
        offset[0] = PyLong_AsSsize_t(PyTuple_GET_ITEM(item, 1));
        offset[1] = PyLong_AsSsize_t(PyTuple_GET_ITEM(item, 2));
        if (PyErr_Occurred()) goto out;
        PyObject *drawn = PyObject_CallNoArgs(draw);
        if (drawn == NULL) goto out;
        double tiebreak = PyFloat_AsDouble(drawn);
        Py_DECREF(drawn);
        if (tiebreak == -1.0 && PyErr_Occurred()) goto out;
        double spread = tiebreak * 2.0;
        order[i].score = distance + spread;
        order[i].x = origin_x + offset[0];
        order[i].y = origin_y + offset[1];
    }
    if (!possible) { Py_INCREF(Py_None); result = Py_None; goto out; }
    for (Py_ssize_t i = 0; i < ntaken; i++) {
        PyObject *item = PySequence_Fast_GET_ITEM(taken, i);
        if (!PyTuple_Check(item) || PyTuple_GET_SIZE(item) != 2) { PyErr_SetString(PyExc_TypeError, "a taken site is ((x, y), size)"); goto out; }
        if (read_pos(PyTuple_GET_ITEM(item, 0), &taken_at[3 * i], &taken_at[3 * i + 1]) < 0) goto out;
        taken_at[3 * i + 2] = PyLong_AsSsize_t(PyTuple_GET_ITEM(item, 1));
        if (taken_at[3 * i + 2] == -1 && PyErr_Occurred()) goto out;
    }
    for (Py_ssize_t i = 0; i < nunits; i++) {
        PyObject *item = PySequence_Fast_GET_ITEM(standing, i);
        if (!PyTuple_Check(item) || PyTuple_GET_SIZE(item) != 3) { PyErr_SetString(PyExc_TypeError, "a unit is (x, y, radius)"); goto out; }
        for (int k = 0; k < 3; k++) {
            units[3 * i + k] = PyFloat_AsDouble(PyTuple_GET_ITEM(item, k));
            if (units[3 * i + k] == -1.0 && PyErr_Occurred()) goto out;
        }
    }
    for (Py_ssize_t i = 0; i < nmines; i++)
        if (read_ints(PySequence_Fast_GET_ITEM(mines, i), &mine_rects[4 * i], 4, "a mine is (x, y, width, height)") < 0) goto out;
    for (Py_ssize_t i = 0; i < nown; i++)
        if (read_ints(PySequence_Fast_GET_ITEM(own, i), &own_rects[4 * i], 4, "a building is (x, y, width, height)") < 0) goto out;
    qsort(order, (size_t)count, sizeof(Candidate), compare_candidates);
    for (Py_ssize_t c = 0; c < count; c++) {
        Py_ssize_t left = order[c].x, top = order[c].y, right = left + size, bottom = top + size;
        int ok = 1;
        for (Py_ssize_t t = 0; ok && t < ntaken; t++) {
            Py_ssize_t reach = size + taken_at[3 * t + 2] - 1;
            Py_ssize_t dx = left - taken_at[3 * t], dy = top - taken_at[3 * t + 1];
            if ((dx < 0 ? -dx : dx) < reach && (dy < 0 ? -dy : dy) < reach) ok = 0;
        }
        if (!ok || left < 0 || top < 0 || right > width || bottom > height) continue;
        for (Py_ssize_t y = top; ok && y < bottom; y++) {
            PyObject *row = PyList_GET_ITEM(rows, y);
            if (!PyList_Check(row) || PyList_GET_SIZE(row) < width) {
                PyErr_SetString(PyExc_ValueError, "a terrain row is not a list of width tiles");
                goto out;
            }
            for (Py_ssize_t x = left; x < right; x++) {
                Py_ssize_t index = y * width + x;
                if (PyList_GET_ITEM(row, x) != grass || blocked.cells[index] || !explored.cells[index]) { ok = 0; break; }
            }
        }
        for (Py_ssize_t u = 0; ok && u < nunits; u++) {
            double ux = units[3 * u], uy = units[3 * u + 1], r = units[3 * u + 2];
            if ((double)left - r < ux && ux < (double)right + r && (double)top - r < uy && uy < (double)bottom + r) ok = 0;
        }
        Py_ssize_t rect[4] = {left, top, size, size};
        for (Py_ssize_t m = 0; ok && m < nmines; m++)
            if (rects_gap(rect, &mine_rects[4 * m]) < clearance) ok = 0;
        for (Py_ssize_t b = 0; ok && b < nown; b++) {
            const Py_ssize_t *other = &own_rects[4 * b];
            Py_ssize_t gap_x = max3(other[0] - right, left - (other[0] + other[2]), 0);
            Py_ssize_t gap_y = max3(other[1] - bottom, top - (other[1] + other[3]), 0);
            if ((gap_x > gap_y ? gap_x : gap_y) < 1) ok = 0;
        }
        if (ok) { result = Py_BuildValue("(nn)", left, top); goto out; }
    }
    Py_INCREF(Py_None);
    result = Py_None;
out:
    PyMem_Free(order);
    PyMem_Free(taken_at);
    PyMem_Free(units);
    PyMem_Free(mine_rects);
    PyMem_Free(own_rects);
    if (explored_open) grid_close(&explored);
    if (blocked_open) grid_close(&blocked);
    Py_XDECREF(ring);
    Py_XDECREF(taken);
    Py_XDECREF(standing);
    Py_XDECREF(mines);
    Py_XDECREF(own);
    return result;
}

/* -- Module ------------------------------------------------------------------------------------ */

static PyMethodDef methods[] = {
    {"find_path_grid", (PyCFunction)(void (*)(void))find_path_grid, METH_FASTCALL, "path.find_path_grid(start, goal, blocked, width, height, max_expansions)"},
    {"find_work_path", (PyCFunction)(void (*)(void))find_work_path, METH_FASTCALL, "path.find_work_path(start, goals, blocked, width, height)"},
    {"distance_field", distance_field, METH_VARARGS, "path.distance_field(starts, blocked, width, height) into an array('d')"},
    {"choose_tree", choose_tree, METH_VARARGS, "worker_ai._choose_tree(start, trees, loaded, remembered, TREES, field, blocked, reach, width, height)"},
    {"region_labels", region_labels, METH_VARARGS, "Regions.__init__'s labels into an array('i'); returns the region count"},
    {"nearest_in_region", nearest_in_region, METH_VARARGS, "Regions.reachable_goal's scan over array('i') labels"},
    {"stamp_discs", (PyCFunction)(void (*)(void))stamp_discs, METH_FASTCALL, "model.World._reveal for every ((x, y), radius) of an iterable"},
    {"or_into", (PyCFunction)(void (*)(void))or_into, METH_FASTCALL, "model.or_into(target, source)"},
    {"stamp_threats", (PyCFunction)(void (*)(void))stamp_threats, METH_FASTCALL, "worker_ai._stamp_units(blocked, units, width, height)"},
    {"any_lit", (PyCFunction)(void (*)(void))any_lit, METH_FASTCALL, "World.any_visible and WorkerKnowledge.sees: any lit tile in (x, y, w, h)"},
    {"stale_tiles", (PyCFunction)(void (*)(void))stale_tiles, METH_FASTCALL, "WorkerKnowledge._stale(visible, terrain rows, remembered, width, height)"},
    {"site_search", site_search, METH_VARARGS, "ai.site_search: the ring, the corner, rng.random, then what ai.site_inputs makes"},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "warband._native", NULL, -1, methods};

PyMODINIT_FUNC PyInit__native(void) {
    SQRT2 = sqrt(2.0);
    DIAGONAL = SQRT2 - 2.0;
    return PyModule_Create(&module);
}
