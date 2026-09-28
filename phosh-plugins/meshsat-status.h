/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * What MeshSat's notifier says on the session bus (net.meshsat.Status): the state of the
 * satellite modem and of the mesh, for the Phosh quick-settings tile and lock-screen widget.
 */
#pragma once

#include <gio/gio.h>

G_BEGIN_DECLS

typedef struct _MeshsatStatus MeshsatStatus;
typedef void (*MeshsatStatusChanged) (MeshsatStatus *status, gpointer user_data);

MeshsatStatus *meshsat_status_new         (MeshsatStatusChanged changed, gpointer user_data);
void           meshsat_status_free        (MeshsatStatus *status);
gboolean       meshsat_status_is_present  (MeshsatStatus *status);
char          *meshsat_status_dup_string  (MeshsatStatus *status, const char *name);
int            meshsat_status_get_int     (MeshsatStatus *status, const char *name);
void           meshsat_status_open        (MeshsatStatus *status, const char *screen);

G_END_DECLS
