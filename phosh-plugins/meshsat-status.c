/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "meshsat-status.h"

#define STATUS_NAME  "net.meshsat.Status"
#define STATUS_PATH  "/net/meshsat/Status"
#define STATUS_IFACE "net.meshsat.Status1"

struct _MeshsatStatus {
  GDBusProxy           *proxy;
  GCancellable         *cancel;
  MeshsatStatusChanged  changed;
  gpointer              user_data;
};


static void
notify_changed (MeshsatStatus *self)
{
  if (self->changed)
    self->changed (self, self->user_data);
}


static void
on_properties_changed (GDBusProxy *proxy, GVariant *changed, GStrv invalidated, gpointer user_data)
{
  notify_changed (user_data);
}


static void
on_owner_changed (GObject *proxy, GParamSpec *pspec, gpointer user_data)
{
  notify_changed (user_data);
}


static void
on_proxy_ready (GObject *source, GAsyncResult *result, gpointer user_data)
{
  g_autoptr (GError) error = NULL;
  GDBusProxy *proxy = g_dbus_proxy_new_for_bus_finish (result, &error);
  MeshsatStatus *self;

  if (proxy == NULL) {
    if (!g_error_matches (error, G_IO_ERROR, G_IO_ERROR_CANCELLED))
      g_warning ("No proxy for %s: %s", STATUS_NAME, error->message);
    return;
  }
  self = user_data;
  self->proxy = proxy;
  g_signal_connect (proxy, "g-properties-changed", G_CALLBACK (on_properties_changed), self);
  g_signal_connect (proxy, "notify::g-name-owner", G_CALLBACK (on_owner_changed), self);
  notify_changed (self);
}


MeshsatStatus *
meshsat_status_new (MeshsatStatusChanged changed, gpointer user_data)
{
  MeshsatStatus *self = g_new0 (MeshsatStatus, 1);

  self->changed = changed;
  self->user_data = user_data;
  self->cancel = g_cancellable_new ();
  g_dbus_proxy_new_for_bus (G_BUS_TYPE_SESSION,
                            G_DBUS_PROXY_FLAGS_DO_NOT_AUTO_START,
                            NULL, STATUS_NAME, STATUS_PATH, STATUS_IFACE,
                            self->cancel, on_proxy_ready, self);
  return self;
}


void
meshsat_status_free (MeshsatStatus *self)
{
  if (self == NULL)
    return;
  self->changed = NULL;
  g_cancellable_cancel (self->cancel);
  g_clear_object (&self->cancel);
  if (self->proxy) {
    g_signal_handlers_disconnect_by_data (self->proxy, self);
    g_clear_object (&self->proxy);
  }
  /* A proxy still being made holds this pointer: it is cancelled and never touches it. */
  g_free (self);
}


gboolean
meshsat_status_is_present (MeshsatStatus *self)
{
  g_autofree char *owner = NULL;

  if (self == NULL || self->proxy == NULL)
    return FALSE;
  owner = g_dbus_proxy_get_name_owner (self->proxy);
  return owner != NULL;
}


char *
meshsat_status_dup_string (MeshsatStatus *self, const char *name)
{
  g_autoptr (GVariant) value = NULL;

  if (!meshsat_status_is_present (self))
    return g_strdup ("");
  value = g_dbus_proxy_get_cached_property (self->proxy, name);
  if (value == NULL || !g_variant_is_of_type (value, G_VARIANT_TYPE_STRING))
    return g_strdup ("");
  return g_variant_dup_string (value, NULL);
}


int
meshsat_status_get_int (MeshsatStatus *self, const char *name)
{
  g_autoptr (GVariant) value = NULL;

  if (!meshsat_status_is_present (self))
    return 0;
  value = g_dbus_proxy_get_cached_property (self->proxy, name);
  if (value == NULL || !g_variant_is_of_type (value, G_VARIANT_TYPE_INT32))
    return 0;
  return g_variant_get_int32 (value);
}


void
meshsat_status_open (MeshsatStatus *self, const char *screen)
{
  if (self == NULL || self->proxy == NULL)
    return;
  g_dbus_proxy_call (self->proxy, "Open", g_variant_new ("(s)", screen),
                     G_DBUS_CALL_FLAGS_NONE, 5000, NULL, NULL, NULL);
}
