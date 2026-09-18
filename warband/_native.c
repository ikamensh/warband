/* warband._native: the grid searches of warband/path.py in C, for the compiled simulation.

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

static PyObject *find_path_grid(PyObject *self, PyObject *args) {
    PyObject *start_obj, *goal_obj, *blocked_obj;
    Py_ssize_t width, height, max_expansions;
    if (!PyArg_ParseTuple(args, "OOOnnn", &start_obj, &goal_obj, &blocked_obj, &width, &height, &max_expansions))
        return NULL;
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

static PyObject *find_work_path(PyObject *self, PyObject *args) {
    PyObject *start_obj, *goals, *blocked_obj;
    Py_ssize_t width, height;
    if (!PyArg_ParseTuple(args, "OO!Onn", &start_obj, &PyDict_Type, &goals, &blocked_obj, &width, &height))
        return NULL;
    if (PyDict_GET_SIZE(goals) == 0) Py_RETURN_NONE;
    Py_ssize_t sx, sy;
    if (read_pos(start_obj, &sx, &sy) < 0) return NULL;
    Py_ssize_t size = width * height, origin = sy * width + sx;
    if (origin < 0 || origin >= size) { PyErr_SetString(PyExc_ValueError, "the start is off the grid"); return NULL; }
    Grid grid;
    if (grid_open(blocked_obj, size, &grid) < 0) return NULL;
    const unsigned char *blocked = grid.cells;
    double *costs = PyMem_Malloc((size_t)size * sizeof(double));
    double *penalty = PyMem_Malloc((size_t)size * sizeof(double));
    unsigned char *is_goal = PyMem_Calloc((size_t)size, 1);
    Py_ssize_t *parents = PyMem_Malloc((size_t)size * sizeof(Py_ssize_t));
    Heap2 frontier = {NULL, 0, 0};
    PyObject *result = NULL;
    if (costs == NULL || penalty == NULL || is_goal == NULL || parents == NULL) { PyErr_NoMemory(); goto out; }
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
    if (best < 0) {
        Py_INCREF(Py_None);
        result = Py_None;
    } else {
        result = route_to(best, origin, parents, width);
    }
out:
    PyMem_Free(frontier.items);
    PyMem_Free(costs);
    PyMem_Free(penalty);
    PyMem_Free(is_goal);
    PyMem_Free(parents);
    grid_close(&grid);
    return result;
}

/* -- distance_field ---------------------------------------------------------------------------- */

static int compare_indices(const void *a, const void *b) {
    Py_ssize_t x = *(const Py_ssize_t *)a, y = *(const Py_ssize_t *)b;
    return (x > y) - (x < y);
}

static PyObject *distance_field(PyObject *self, PyObject *args) {
    PyObject *starts_obj, *blocked_obj;
    Py_ssize_t width, height;
    if (!PyArg_ParseTuple(args, "OOnn", &starts_obj, &blocked_obj, &width, &height))
        return NULL;
    Py_ssize_t size = width * height;
    PyObject *starts = PySequence_Fast(starts_obj, "the starts are a sequence of flat indices");
    if (starts == NULL) return NULL;
    Py_ssize_t count = PySequence_Fast_GET_SIZE(starts);
    Grid grid;
    if (grid_open(blocked_obj, size, &grid) < 0) { Py_DECREF(starts); return NULL; }
    const unsigned char *blocked = grid.cells;
    double *distances = PyMem_Malloc((size_t)size * sizeof(double));
    Py_ssize_t *sorted = PyMem_Malloc((size_t)(count ? count : 1) * sizeof(Py_ssize_t));
    Heap2 frontier = {NULL, 0, 0};
    PyObject *result = NULL;
    if (distances == NULL || sorted == NULL) { PyErr_NoMemory(); goto out; }
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
    result = PyList_New(size);
    if (result == NULL) goto out;
    PyObject *infinity = PyFloat_FromDouble(INFINITY);
    if (infinity == NULL) { Py_CLEAR(result); goto out; }
    for (Py_ssize_t i = 0; i < size; i++) {
        PyObject *item;
        if (distances[i] == INFINITY) {
            Py_INCREF(infinity);
            item = infinity;
        } else if ((item = PyFloat_FromDouble(distances[i])) == NULL) {
            Py_DECREF(infinity);
            Py_CLEAR(result);
            goto out;
        }
        PyList_SET_ITEM(result, i, item);
    }
    Py_DECREF(infinity);
out:
    PyMem_Free(frontier.items);
    PyMem_Free(distances);
    PyMem_Free(sorted);
    grid_close(&grid);
    Py_DECREF(starts);
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

/* -- Module ------------------------------------------------------------------------------------ */

static PyMethodDef methods[] = {
    {"find_path_grid", find_path_grid, METH_VARARGS, "path.find_path_grid(start, goal, blocked, width, height, max_expansions)"},
    {"find_work_path", find_work_path, METH_VARARGS, "path.find_work_path(start, goals, blocked, width, height)"},
    {"distance_field", distance_field, METH_VARARGS, "path.distance_field(starts, blocked, width, height)"},
    {"region_labels", region_labels, METH_VARARGS, "Regions.__init__'s labels into an array('i'); returns the region count"},
    {"nearest_in_region", nearest_in_region, METH_VARARGS, "Regions.reachable_goal's scan over array('i') labels"},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "warband._native", NULL, -1, methods};

PyMODINIT_FUNC PyInit__native(void) {
    SQRT2 = sqrt(2.0);
    DIAGONAL = SQRT2 - 2.0;
    return PyModule_Create(&module);
}
