/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * MeshSat on Phosh's lock screen: the satellite signal and the mesh, in the words of the
 * app's Home lanes, without unlocking the phone. A plain GtkBox: Phosh's lock-screen plugins
 * need nothing of Phosh but the extension point's name.
 */
#include <gtk/gtk.h>
#include <gio/gio.h>

#include "meshsat-status.h"

#define EXTENSION_POINT "phosh-lockscreen-widget"
#define PLUGIN_NAME     "meshsat-lockscreen"

#define MESHSAT_TYPE_LOCKSCREEN (meshsat_lockscreen_get_type ())
G_DECLARE_FINAL_TYPE (MeshsatLockscreen, meshsat_lockscreen, MESHSAT, LOCKSCREEN, GtkBox)

struct _MeshsatLockscreen {
  GtkBox         parent;

  MeshsatStatus *status;
  GtkWidget     *icon;
  GtkWidget     *satellite;
  GtkWidget     *mesh;
};

G_DEFINE_TYPE (MeshsatLockscreen, meshsat_lockscreen, GTK_TYPE_BOX)

char **g_io_phosh_plugin_meshsat_lockscreen_query (void);


static void
update (MeshsatLockscreen *self)
{
  g_autofree char *icon = NULL;
  g_autofree char *satellite = NULL;
  g_autofree char *mesh = NULL;

  if (!meshsat_status_is_present (self->status)) {
    gtk_image_set_from_icon_name (GTK_IMAGE (self->icon), "meshsat-iridium-0-symbolic", GTK_ICON_SIZE_DND);
    gtk_label_set_text (GTK_LABEL (self->satellite), "MeshSat is not running.");
    gtk_label_set_text (GTK_LABEL (self->mesh), "");
    gtk_widget_hide (self->mesh);
    return;
  }
  icon = meshsat_status_dup_string (self->status, "IconName");
  satellite = meshsat_status_dup_string (self->status, "SatelliteDetail");
  mesh = meshsat_status_dup_string (self->status, "MeshDetail");
  gtk_image_set_from_icon_name (GTK_IMAGE (self->icon), (icon && *icon) ? icon : "meshsat-iridium-0-symbolic", GTK_ICON_SIZE_DND);
  gtk_label_set_text (GTK_LABEL (self->satellite), satellite);
  gtk_label_set_text (GTK_LABEL (self->mesh), mesh);
  gtk_widget_set_visible (self->mesh, mesh && *mesh);
}


static void
on_status_changed (MeshsatStatus *status, gpointer user_data)
{
  update (MESHSAT_LOCKSCREEN (user_data));
}


static void
meshsat_lockscreen_finalize (GObject *object)
{
  MeshsatLockscreen *self = MESHSAT_LOCKSCREEN (object);

  g_clear_pointer (&self->status, meshsat_status_free);
  G_OBJECT_CLASS (meshsat_lockscreen_parent_class)->finalize (object);
}


static void
meshsat_lockscreen_class_init (MeshsatLockscreenClass *klass)
{
  G_OBJECT_CLASS (klass)->finalize = meshsat_lockscreen_finalize;
  gtk_widget_class_set_css_name (GTK_WIDGET_CLASS (klass), "meshsat-lockscreen");
}


static GtkWidget *
line (const char *text, gboolean title)
{
  GtkWidget *label = gtk_label_new (text);

  gtk_label_set_xalign (GTK_LABEL (label), 0.0);
  gtk_label_set_line_wrap (GTK_LABEL (label), TRUE);
  if (title) {
    PangoAttrList *attrs = pango_attr_list_new ();

    pango_attr_list_insert (attrs, pango_attr_weight_new (PANGO_WEIGHT_BOLD));
    gtk_label_set_attributes (GTK_LABEL (label), attrs);
    pango_attr_list_unref (attrs);
  } else {
    gtk_style_context_add_class (gtk_widget_get_style_context (label), "dim-label");
  }
  gtk_widget_show (label);
  return label;
}


static void
meshsat_lockscreen_init (MeshsatLockscreen *self)
{
  GtkWidget *texts = gtk_box_new (GTK_ORIENTATION_VERTICAL, 2);

  gtk_orientable_set_orientation (GTK_ORIENTABLE (self), GTK_ORIENTATION_HORIZONTAL);
  gtk_box_set_spacing (GTK_BOX (self), 12);
  g_object_set (self, "margin", 12, NULL);

  self->icon = gtk_image_new_from_icon_name ("meshsat-iridium-0-symbolic", GTK_ICON_SIZE_DND);
  gtk_widget_set_valign (self->icon, GTK_ALIGN_START);
  gtk_widget_show (self->icon);
  gtk_box_pack_start (GTK_BOX (self), self->icon, FALSE, FALSE, 0);

  gtk_box_pack_start (GTK_BOX (texts), line ("MeshSat", TRUE), FALSE, FALSE, 0);
  self->satellite = line ("", FALSE);
  self->mesh = line ("", FALSE);
  gtk_box_pack_start (GTK_BOX (texts), self->satellite, FALSE, FALSE, 0);
  gtk_box_pack_start (GTK_BOX (texts), self->mesh, FALSE, FALSE, 0);
  gtk_widget_show (texts);
  gtk_box_pack_start (GTK_BOX (self), texts, TRUE, TRUE, 0);

  self->status = meshsat_status_new (on_status_changed, self);
  update (self);
}


void
g_io_module_load (GIOModule *module)
{
  g_type_module_use (G_TYPE_MODULE (module));
  g_io_extension_point_implement (EXTENSION_POINT, MESHSAT_TYPE_LOCKSCREEN, PLUGIN_NAME, 10);
}


void
g_io_module_unload (GIOModule *module)
{
}


char **
g_io_phosh_plugin_meshsat_lockscreen_query (void)
{
  char *extension_points[] = { EXTENSION_POINT, NULL };

  return g_strdupv (extension_points);
}
