/* rcb_mypaint.c - a tiny C shim over libmypaint 1.6.1 (ISC) for Python ctypes (maniskill-paint, family C: oil/acrylic).
 *
 * A fixed-size tiled surface that implements libmypaint's MyPaintSurface2 interface (the library's own
 * MyPaintFixedTiledSurface only implements the legacy MyPaintSurface, which has no barrel rotation), plus brush helpers.
 * Pixels are libmypaint's native format: 16-bit premultiplied RGBA with 1.0 = 1 << 15, tiles of 64 x 64 px.
 * The surface starts fully transparent (an empty layer over the paper; the Python side composites it over the paper colour).
 * Everything is single-threaded (libmypaint is built without OpenMP) so the result is a deterministic function of the call
 * sequence; the brush RNG is libmypaint's own (seeded with 1000 in mypaint_brush_new, re-created with the brush). */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#include <mypaint-brush.h>
#include <mypaint-tiled-surface.h>

typedef struct {
    MyPaintTiledSurface2 parent;
    size_t tile_bytes;      /* bytes per tile */
    uint16_t *tiles;        /* tiles_w * tiles_h tiles, row-major by tile */
    uint16_t *null_tile;    /* handed out for requests outside the surface; writes are discarded */
    int tiles_w, tiles_h, width, height, ts;
} RcbSurface;

static void tile_start(MyPaintTiledSurface2 *ts, MyPaintTileRequest *req) {
    RcbSurface *s = (RcbSurface *)ts;
    if (req->tx < 0 || req->ty < 0 || req->tx >= s->tiles_w || req->ty >= s->tiles_h) {
        req->buffer = s->null_tile;
    } else {
        req->buffer = s->tiles + ((size_t)req->ty * s->tiles_w + req->tx) * (s->tile_bytes / sizeof(uint16_t));
    }
}

static void tile_end(MyPaintTiledSurface2 *ts, MyPaintTileRequest *req) {
    RcbSurface *s = (RcbSurface *)ts;
    if (req->buffer == s->null_tile) memset(s->null_tile, 0, s->tile_bytes);
}

static void surface_destroy(MyPaintSurface *surf) {
    RcbSurface *s = (RcbSurface *)surf;
    mypaint_tiled_surface2_destroy(&s->parent);
    free(s->tiles); free(s->null_tile); free(s);
}

RcbSurface *rcb_surface_new(int width, int height) {
    RcbSurface *s = (RcbSurface *)calloc(1, sizeof(RcbSurface));
    if (!s) return NULL;
    mypaint_tiled_surface2_init(&s->parent, tile_start, tile_end);
    s->parent.parent.parent.destroy = surface_destroy;
    s->ts = s->parent.tile_size;
    s->width = width; s->height = height;
    s->tiles_w = (width + s->ts - 1) / s->ts; s->tiles_h = (height + s->ts - 1) / s->ts;
    s->tile_bytes = (size_t)s->ts * s->ts * 4 * sizeof(uint16_t);
    s->tiles = (uint16_t *)calloc((size_t)s->tiles_w * s->tiles_h, s->tile_bytes);
    s->null_tile = (uint16_t *)calloc(1, s->tile_bytes);
    if (!s->tiles || !s->null_tile) { free(s->tiles); free(s->null_tile); free(s); return NULL; }
    return s;
}

void rcb_surface_free(RcbSurface *s) { if (s) mypaint_surface_unref((MyPaintSurface *)s); }
int rcb_surface_tile_size(RcbSurface *s) { return s->ts; }

void rcb_surface_clear(RcbSurface *s) { memset(s->tiles, 0, (size_t)s->tiles_w * s->tiles_h * s->tile_bytes); }

/* out / in: height x width x 4 uint16 (premultiplied RGBA, 1.0 = 32768), row-major */
void rcb_surface_read(RcbSurface *s, uint16_t *out) {
    const int ts = s->ts;
    for (int y = 0; y < s->height; y++) {
        const int ty = y / ts, yy = y % ts;
        for (int tx = 0; tx < s->tiles_w; tx++) {
            const int x0 = tx * ts;
            int n = s->width - x0; if (n > ts) n = ts;
            const uint16_t *src = s->tiles + ((size_t)ty * s->tiles_w + tx) * (s->tile_bytes / 2) + (size_t)yy * ts * 4;
            memcpy(out + ((size_t)y * s->width + x0) * 4, src, (size_t)n * 4 * sizeof(uint16_t));
        }
    }
}

void rcb_surface_write(RcbSurface *s, const uint16_t *in) {
    const int ts = s->ts;
    for (int y = 0; y < s->height; y++) {
        const int ty = y / ts, yy = y % ts;
        for (int tx = 0; tx < s->tiles_w; tx++) {
            const int x0 = tx * ts;
            int n = s->width - x0; if (n > ts) n = ts;
            uint16_t *dst = s->tiles + ((size_t)ty * s->tiles_w + tx) * (s->tile_bytes / 2) + (size_t)yy * ts * 4;
            memcpy(dst, in + ((size_t)y * s->width + x0) * 4, (size_t)n * 4 * sizeof(uint16_t));
        }
    }
}

MyPaintBrush *rcb_brush_new(const char *json) {
    MyPaintBrush *b = mypaint_brush_new();   /* no smudge buckets: the smudge state lives in the brush states, which a reset clears */
    if (!b) return NULL;
    if (!mypaint_brush_from_string(b, json)) { mypaint_brush_unref(b); return NULL; }
    mypaint_brush_new_stroke(b);
    return b;
}

void rcb_brush_free(MyPaintBrush *b) { if (b) mypaint_brush_unref(b); }

int rcb_setting_id(const char *cname) { return (int)mypaint_brush_setting_from_cname(cname); }

void rcb_brush_set_base(MyPaintBrush *b, int id, float v) { mypaint_brush_set_base_value(b, (MyPaintBrushSetting)id, v); }

float rcb_brush_get_base(MyPaintBrush *b, int id) { return mypaint_brush_get_base_value(b, (MyPaintBrushSetting)id); }

void rcb_brush_reset(MyPaintBrush *b) { mypaint_brush_reset(b); mypaint_brush_new_stroke(b); }

void rcb_brush_new_stroke(MyPaintBrush *b) { mypaint_brush_new_stroke(b); }

/* One motion event (one physics-step sample). Returns 1 if the brush asked for a stroke split (MyPaint's "stroke done"). */
int rcb_stroke_to(MyPaintBrush *b, RcbSurface *s, float x, float y, float pressure, float xtilt, float ytilt, double dtime,
                  float barrel_rotation, int *roi) {
    MyPaintRectangle rect[1];
    MyPaintRectangles rois = {1, rect};
    mypaint_surface_begin_atomic((MyPaintSurface *)s);
    int r = mypaint_brush_stroke_to_2(b, (MyPaintSurface2 *)s, x, y, pressure, xtilt, ytilt, dtime, 1.0f, 0.0f, barrel_rotation);
    mypaint_surface2_end_atomic((MyPaintSurface2 *)s, &rois);
    if (roi) { roi[0] = rect[0].x; roi[1] = rect[0].y; roi[2] = rect[0].width; roi[3] = rect[0].height; }
    return r;
}
