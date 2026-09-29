# SPDX-License-Identifier: GPL-3.0-or-later
"""A QR code drawn as MeshSat Android draws My card's (ContactCards.kt:263-291, zxing's
BarcodeEncoder): error correction L, a quiet zone of four modules, black on white, scaled by
whole pixels per module and centred, on a white square with 8 dp corners and 8 dp padding."""
import math

from gi.repository import Gtk

from . import theme
from .widgets import name_widget


def matrix(value: str):
    """The modules (True = dark), quiet zone included, or None without python3-qrcode."""
    try:
        import qrcode  # noqa: PLC0415
        from qrcode.constants import ERROR_CORRECT_L  # noqa: PLC0415
    except ImportError:
        return None
    code = qrcode.QRCode(error_correction=ERROR_CORRECT_L, border=4, box_size=1)
    code.add_data(value.encode("utf-8"))
    code.make(fit=True)
    return code.get_matrix()


class QRView(Gtk.DrawingArea):
    def __init__(self, value: str, size_dp: int = 260, name: str = ""):
        super().__init__(accessible_role=Gtk.AccessibleRole.IMG)
        self.modules = matrix(value)
        side = theme.dp(size_dp)
        self.set_content_width(side)
        self.set_content_height(side)
        self.set_halign(Gtk.Align.CENTER)
        self.set_draw_func(self.draw)
        if name:
            name_widget(self, name)

    def draw(self, _area, cr, width, height) -> None:
        radius, pad = theme.dp(8), theme.dp(8)
        cr.new_sub_path()
        cr.arc(width - radius, radius, radius, -math.pi / 2, 0)
        cr.arc(width - radius, height - radius, radius, 0, math.pi / 2)
        cr.arc(radius, height - radius, radius, math.pi / 2, math.pi)
        cr.arc(radius, radius, radius, math.pi, 3 * math.pi / 2)
        cr.close_path()
        cr.set_source_rgb(1, 1, 1)
        cr.fill()
        if not self.modules:
            return
        count = len(self.modules)
        scale = max(1, int((min(width, height) - 2 * pad) // count))
        left = (width - count * scale) // 2
        top = (height - count * scale) // 2
        cr.set_source_rgb(0, 0, 0)
        for y, row in enumerate(self.modules):
            for x, dark in enumerate(row):
                if dark:
                    cr.rectangle(left + x * scale, top + y * scale, scale, scale)
        cr.fill()
