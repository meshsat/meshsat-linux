/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * MeshSat in Phosh's quick settings: the satellite signal (0 to 5 bars) or, without a modem,
 * the mesh and its node count; a tap opens the app. It is what MeshSat Android's status-bar
 * icon is there: Phosh's top bar takes no icons from applications.
 *
 * Phosh does not ship the headers of its quick settings, so this looks the two types up by
 * name when Phosh loads the module (PhoshQuickSetting, PhoshStatusIcon) and uses only their
 * properties ("status-icon", "active", "icon-name", "info") and the "clicked" signal: no
 * symbol of Phosh is linked, and a Phosh that changed a struct does not break it. Outside
 * Phosh the types do not exist and the module implements nothing.
 */
#include <gtk/gtk.h>
#include <gio/gio.h>

#include "meshsat-status.h"

#define EXTENSION_POINT "phosh-quick-setting-widget"
#define PLUGIN_NAME     "meshsat-quick-setting"
#define STATE_KEY       "meshsat-state"

typedef struct {
  MeshsatStatus *status;
  GObject       *icon;
} State;

char **g_io_phosh_plugin_meshsat_quick_setting_query (void);


static void
state_free (gpointer data)
{
  State *state = data;

  meshsat_status_free (state->status);
  g_free (state);
}


static void
update (GObject *self)
{
  State *state = g_object_get_data (self, STATE_KEY);
  g_autofree char *icon = NULL;
  g_autofree char *satellite = NULL;
  g_autofree char *mesh = NULL;
  g_autofree char *label = NULL;
  gboolean working;

  if (state == NULL || state->icon == NULL)
    return;
  icon = meshsat_status_dup_string (state->status, "IconName");
  satellite = meshsat_status_dup_string (state->status, "SatelliteState");
  mesh = meshsat_status_dup_string (state->status, "MeshState");
  /* The words are the notifier's (TileLabel), so they change without a rebuild of this. */
  label = meshsat_status_dup_string (state->status, "TileLabel");
  if (label == NULL || *label == '\0') {
    g_free (label);
    if (!meshsat_status_is_present (state->status))
      label = g_strdup ("MeshSat: off");
    else if (g_strcmp0 (satellite, "working") == 0)
      label = g_strdup_printf ("Satellite: %d/5", meshsat_status_get_int (state->status, "SatelliteBars"));
    else if (g_strcmp0 (mesh, "working") == 0)
      label = g_strdup_printf ("Mesh: %d nodes", meshsat_status_get_int (state->status, "MeshNodes"));
    else
      label = g_strdup ("MeshSat: no node");
  }
  working = g_strcmp0 (satellite, "working") == 0 || g_strcmp0 (mesh, "working") == 0;
  g_object_set (state->icon,
                "icon-name", (icon && *icon) ? icon : "meshsat-iridium-0-symbolic",
                "info", label,
                NULL);
  g_object_set (self, "active", working, NULL);
}


static void
on_status_changed (MeshsatStatus *status, gpointer user_data)
{
  update (G_OBJECT (user_data));
}


static void
on_clicked (GObject *self)
{
  State *state = g_object_get_data (self, STATE_KEY);

  if (state)
    meshsat_status_open (state->status, "home");
}


static void
instance_init (GTypeInstance *instance, gpointer klass)
{
  GObject *self = G_OBJECT (instance);
  State *state = g_new0 (State, 1);
  GType icon_type = g_type_from_name ("PhoshStatusIcon");

  g_object_set_data_full (self, STATE_KEY, state, state_free);
  if (icon_type != 0) {
    state->icon = g_object_new (icon_type, "visible", TRUE, "icon-size", GTK_ICON_SIZE_MENU, NULL);
    g_object_set (self, "status-icon", state->icon, NULL);
  }
  g_signal_connect (self, "clicked", G_CALLBACK (on_clicked), NULL);
  state->status = meshsat_status_new (on_status_changed, self);
  update (self);
}


static GType
meshsat_quick_setting_get_type (void)
{
  static GType type = 0;

  if (type == 0) {
    GType parent = g_type_from_name ("PhoshQuickSetting");
    GTypeQuery query;
    GTypeInfo info = { 0, };

    if (parent == 0)
      return 0;
    g_type_query (parent, &query);
    info.class_size = query.class_size;
    info.instance_size = query.instance_size;
    info.instance_init = instance_init;
    type = g_type_register_static (parent, "MeshsatQuickSetting", &info, 0);
  }
  return type;
}


void
g_io_module_load (GIOModule *module)
{
  GType type;

  g_type_module_use (G_TYPE_MODULE (module));
  type = meshsat_quick_setting_get_type ();
  if (type == 0) {
    g_debug ("No PhoshQuickSetting type: not loaded by Phosh, nothing to implement");
    return;
  }
  g_io_extension_point_implement (EXTENSION_POINT, type, PLUGIN_NAME, 10);
}


void
g_io_module_unload (GIOModule *module)
{
}


char **
g_io_phosh_plugin_meshsat_quick_setting_query (void)
{
  char *extension_points[] = { EXTENSION_POINT, NULL };

  return g_strdupv (extension_points);
}
