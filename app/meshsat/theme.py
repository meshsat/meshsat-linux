# SPDX-License-Identifier: GPL-3.0-or-later
"""The MeshSat look, as the Android app has it and the iOS app mirrors it: the tokens of
Android's ui/theme/Color.kt (the iOS Color.swift keeps the same names), IBM Plex, Material 3
measures. Dark only, as both apps; night mode is a colour matrix drawn over the whole window
(see NightFilter in __main__), so every colour here is a day colour.

Measures are written in the Android app's dp and scaled once, by SCALE: the reference phone
is about 400 dp wide, a PinePhone is 360 px, so 1 dp = 0.9 px keeps the proportions of the
Android screens on the smaller screen. MESHSAT_APP_SCALE overrides it (1.0 = 1 dp per px)."""
import os

from gi.repository import Gdk, Gtk

SCALE = float(os.environ.get("MESHSAT_APP_SCALE", "0.9"))

# Colour.kt tokens
SPACE_BLACK = "#040406"
SIGNAL_ORANGE = "#F96118"
ORANGE_LIGHT = "#FF7C3B"
OFF_WHITE = "#F7F7F4"
SURFACE = "#15151B"
SURFACE_LIGHT = "#24242C"
BORDER = "#24242C"
TEXT_PRIMARY = "#EBEBEE"
TEXT_SECONDARY = "#B4B4BD"
TEXT_MUTED = "#8A8A96"
GREEN = "#34D399"
AMBER = "#FBBF24"
RED = "#F87171"
BLUE = "#8FB8DE"
IRIDIUM = "#B9A7E6"
MESH = "#C8B89A"
SMS = "#E0B458"
HUB = "#8FB8DE"
# Material roles
ON_PRIMARY = "#040406"  # text on orange: always ink, never white
PRIMARY_CONTAINER = "#3D1405"
ON_PRIMARY_CONTAINER = "#FFC4A6"
SURFACE_LOW = "#0B0B0F"
SURFACE_HIGH = "#1B1B22"
OUTLINE = "#3A3A44"
ERROR_CONTAINER = "#3B1414"
ON_ERROR_CONTAINER = "#FCA5A5"
TAG_MESH = "#26231D"
TAG_SATELLITE = "#24213A"
TAG_HUB = "#17232F"
TAG_SMS = "#2B2515"

FONT = "IBM Plex Sans"
MONO = "IBM Plex Mono"

# Android ColorMatrix rows (4 x 5, offsets in 0..255), drawn by widgets.Filtered.
# Night mode (ui/theme/NightMode.kt): red only, 0.24 R + 0.47 G + 0.09 B.
NIGHT_MATRIX = (0.24, 0.47, 0.09, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0)
# The map's dark tiles (map/MapTiles.kt, MESHSAT-1249): OpenStreetMap's light tiles inverted, hue
# turned by 180 degrees so water stays blue and parks green, then toned to the app's surfaces.
DARK_TILES_MATRIX = (0.5051, -1.2584, -0.1267, 0, 234.40, -0.3749, -0.3784, -0.1267, 0, 234.40, -0.3749, -1.2584, 0.7533, 0, 234.40, 0, 0, 0, 1, 0)

LANES = {"satellite": IRIDIUM, "mesh": MESH, "sms": SMS, "hub": HUB, "location": GREEN, "radio": OFF_WHITE}

# Every token, by name and by value: colours are given to widgets as CSS classes (.fg-x, .bg-x),
# never as per-widget providers, which GTK 4 does not apply to symbolic icons.
TOKENS = {name: value for name, value in list(globals().items()) if name.isupper() and isinstance(value, str) and value.startswith("#")}
CLASSES = {}
for _name, _value in TOKENS.items():
    CLASSES.setdefault(_value, _name.lower().replace("_", "-"))


def lane_colour(lane: str) -> str:
    return LANES.get(lane, TEXT_MUTED)


def class_of(colour: str) -> str | None:
    return CLASSES.get(colour)


def dp(value: float) -> int:
    """Android dp to whole pixels on this screen."""
    return int(round(value * SCALE))


def px(value: float) -> str:
    """Android dp (or sp) to a CSS length."""
    return f"{value * SCALE:.1f}px"


def css() -> str:
    colours = "\n".join(f".fg-{slug}.fg-{slug} {{ color: {value}; }} .bg-{slug}.bg-{slug} {{ background-color: {value}; }}" for value, slug in CLASSES.items())
    return f"""
:root {{ --window-bg-color: {SPACE_BLACK}; --window-fg-color: {TEXT_PRIMARY}; --view-bg-color: {SPACE_BLACK}; --view-fg-color: {TEXT_PRIMARY};
  --dialog-bg-color: {SURFACE_HIGH}; --dialog-fg-color: {TEXT_PRIMARY}; --popover-bg-color: {SURFACE_HIGH}; --popover-fg-color: {TEXT_PRIMARY};
  --accent-bg-color: {SIGNAL_ORANGE}; --accent-fg-color: {ON_PRIMARY}; --accent-color: {SIGNAL_ORANGE}; --headerbar-bg-color: {SURFACE}; --headerbar-fg-color: {TEXT_PRIMARY};
  --sheet-bg-color: {SURFACE}; --sheet-fg-color: {TEXT_PRIMARY}; }}
bottom-sheet > sheet {{ background-color: {SURFACE}; }}
window {{ background-color: {SPACE_BLACK}; color: {TEXT_PRIMARY}; font-family: "{FONT}", sans-serif; font-size: {px(16)}; }}
* {{ outline-width: 0; -gtk-icon-style: symbolic; }}
label {{ color: {TEXT_PRIMARY}; }}
toast {{ background-color: {SURFACE_HIGH}; border: 1px solid {BORDER}; border-radius: {px(8)}; box-shadow: none; }}
toast label {{ color: {TEXT_PRIMARY}; font-size: {px(14)}; }}
.sheet {{ padding: {px(16)} {px(16)} {px(24)} {px(16)}; }}
.mono {{ font-family: "{MONO}", monospace; }}
.display-small {{ font-size: {px(32)}; font-weight: 600; }}
.headline-large {{ font-size: {px(28)}; font-weight: 600; }}
.headline-medium {{ font-size: {px(22)}; font-weight: 600; }}
.headline-small {{ font-size: {px(19)}; font-weight: 600; }}
.title-large {{ font-size: {px(18)}; font-weight: 600; }}
.title-medium {{ font-size: {px(16)}; font-weight: 500; }}
.title-small {{ font-size: {px(14)}; font-weight: 500; }}
.body-large {{ font-size: {px(16)}; }}
.body-medium {{ font-size: {px(14)}; }}
.body-small {{ font-size: {px(12)}; }}
.label-large {{ font-size: {px(14)}; font-weight: 500; }}
.label-medium {{ font-size: {px(12)}; font-weight: 500; }}
.strip {{ background-color: {SURFACE}; min-height: {px(36)}; padding: 0 {px(16)}; }}
.strip label {{ font-family: "{MONO}", monospace; font-size: {px(12)}; font-weight: 500; color: {TEXT_SECONDARY}; }}
.banner {{ background-color: {AMBER}; padding: {px(12)} {px(16)}; border-radius: 0; border: none; box-shadow: none; }}
.banner label {{ color: {SPACE_BLACK}; font-size: {px(16)}; }}
.banner.sos {{ background-color: {RED}; }}
.banner.sos.test {{ background-color: {AMBER}; }}
.card {{ background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: {px(8)}; }}
.card.sos-on {{ border-color: {RED}; }}
.card.sos-test {{ border-color: {AMBER}; }}
.tonal {{ background-color: {SURFACE_LIGHT}; border-radius: {px(20)}; padding: 0 {px(16)}; min-height: {px(40)}; border: none; box-shadow: none; }}
.tonal label {{ color: {OFF_WHITE}; font-size: {px(14)}; font-weight: 500; }}
.card-pad {{ padding: {px(12)}; }}
.lane-row {{ padding: {px(12)} {px(12)} {px(8)} {px(12)}; min-height: {px(76)}; }}
.lane-sep {{ background-color: {BORDER}; min-height: 1px; }}
.flat {{ background: none; border: none; box-shadow: none; padding: 0; border-radius: 0; }}
button label.body-large, button label.body-medium, button label.body-small {{ font-weight: 400; }}
.flat:hover {{ background-color: {SURFACE_LIGHT}; }}
.icon-button {{ background: none; border: none; box-shadow: none; padding: {px(12)}; min-width: {px(24)}; min-height: {px(24)}; border-radius: {px(24)}; color: {TEXT_PRIMARY}; }}
.icon-button:hover {{ background-color: {SURFACE_LIGHT}; }}
.round {{ background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: {px(24)}; min-width: {px(48)}; min-height: {px(48)}; padding: 0; box-shadow: none; color: {TEXT_PRIMARY}; }}
.nav {{ background-color: {SURFACE}; min-height: {px(80)}; padding: {px(12)} 0 {px(16)} 0; }}
.nav-pill {{ border-radius: {px(16)}; min-width: {px(64)}; min-height: {px(32)}; }}
.nav-item.active .nav-pill {{ background-color: {SURFACE_LIGHT}; }}
.nav-label {{ font-size: {px(12)}; font-weight: 500; color: {TEXT_MUTED}; margin-top: {px(4)}; }}
.nav-item.active .nav-label {{ color: {OFF_WHITE}; }}
.nav-icon {{ color: {TEXT_MUTED}; }}
.nav-item.active .nav-icon {{ color: {OFF_WHITE}; }}
.nav-item:hover, .nav-item:active, .nav-item:focus, .lane-row:hover, .flat.nav-item:hover {{ background: none; }}
.chip {{ background-color: {SURFACE}; border: 1px solid {OUTLINE}; border-radius: {px(8)}; padding: 0 {px(14)}; min-height: {px(32)}; color: {TEXT_PRIMARY}; font-size: {px(14)}; font-weight: 500; box-shadow: none; }}
.chip.selected {{ background-color: {SURFACE_LIGHT}; border-color: {SURFACE_LIGHT}; }}
.chip.filter-chip {{ font-size: {px(12)}; font-weight: 400; }}
.chip.filter-chip.selected {{ background-color: alpha({SIGNAL_ORANGE}, 0.2); border-color: transparent; }}
.tag {{ border-radius: {px(4)}; padding: {px(2)} {px(6)}; font-size: {px(12)}; font-weight: 500; }}
.tag-mesh {{ background-color: {TAG_MESH}; color: {MESH}; }}
.tag-satellite {{ background-color: {TAG_SATELLITE}; color: {IRIDIUM}; }}
.tag-hub {{ background-color: {TAG_HUB}; color: {HUB}; }}
.tag-sms {{ background-color: {TAG_SMS}; color: {SMS}; }}
.count {{ background-color: {SURFACE_LIGHT}; border-radius: {px(4)}; padding: {px(2)} {px(6)}; font-size: {px(12)}; color: {TEXT_SECONDARY}; font-family: "{MONO}", monospace; }}
.filled {{ background-color: {SIGNAL_ORANGE}; border-radius: {px(20)}; padding: 0 {px(24)}; min-height: {px(40)}; border: none; box-shadow: none; }}
.filled label {{ color: {ON_PRIMARY}; font-size: {px(14)}; font-weight: 500; }}
.filled:hover {{ background-color: {ORANGE_LIGHT}; }}
.filled:disabled {{ background-color: alpha({OFF_WHITE}, 0.12); }}
.filled:disabled label {{ color: alpha({OFF_WHITE}, 0.38); }}
.outlined {{ background: none; border: 1px solid {OUTLINE}; border-radius: {px(20)}; padding: 0 {px(24)}; min-height: {px(40)}; box-shadow: none; }}
.outlined label {{ color: {SIGNAL_ORANGE}; font-size: {px(14)}; font-weight: 500; }}
.outlined.danger {{ border-color: {RED}; background-color: {ERROR_CONTAINER}; min-height: {px(56)}; }}
.outlined.danger label {{ color: {RED}; font-size: {px(18)}; font-weight: 600; }}
.textbutton {{ background: none; border: none; box-shadow: none; padding: {px(8)} {px(12)}; }}
.textbutton label {{ color: {SIGNAL_ORANGE}; font-size: {px(14)}; font-weight: 500; }}
.textbutton.off-white label {{ color: {OFF_WHITE}; }}
.field {{ background-color: {SPACE_BLACK}; border: 1px solid {OUTLINE}; border-radius: {px(4)}; padding: 0 {px(14)}; min-height: {px(56)}; color: {TEXT_PRIMARY}; font-size: {px(16)}; caret-color: {SIGNAL_ORANGE}; }}
.field:focus-within {{ border: 2px solid {SIGNAL_ORANGE}; }}
.bubble {{ background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: {px(12)} {px(12)} {px(12)} {px(4)}; padding: {px(10)}; }}
.bubble.mine {{ background-color: alpha({SIGNAL_ORANGE}, 0.15); border-color: alpha({SIGNAL_ORANGE}, 0.3); border-radius: {px(12)} {px(12)} {px(4)} {px(12)}; }}
.icon-button.small {{ padding: {px(4)}; min-width: {px(12)}; min-height: {px(12)}; border-radius: {px(10)}; }}
.search {{ background-color: {SPACE_BLACK}; border: 1px solid {BORDER}; border-radius: {px(4)}; padding: 0 {px(8)}; min-height: {px(48)}; }}
.search:focus-within {{ border-color: {SIGNAL_ORANGE}; }}
.search entry {{ background: none; border: none; box-shadow: none; color: {TEXT_PRIMARY}; font-size: {px(14)}; caret-color: {SIGNAL_ORANGE}; }}
.state-tag {{ border-radius: {px(4)}; padding: {px(2)} {px(6)}; }}
.state-tag.tint-green {{ background-color: alpha({GREEN}, 0.12); }}
.state-tag.tint-amber {{ background-color: alpha({AMBER}, 0.12); }}
.state-tag.tint-red {{ background-color: alpha({RED}, 0.12); }}
.state-tag.tint-teal {{ background-color: alpha({SIGNAL_ORANGE}, 0.12); }}
.state-tag.tint-muted {{ background-color: alpha({TEXT_MUTED}, 0.12); }}
.state-tag.tint-mesh {{ background-color: alpha({MESH}, 0.15); }}
.state-tag.tint-satellite {{ background-color: alpha({IRIDIUM}, 0.15); }}
.state-tag.tint-sms {{ background-color: alpha({SMS}, 0.15); }}
.state-tag.tint-hub {{ background-color: alpha({HUB}, 0.15); }}
.score-tag {{ border-radius: {px(6)}; padding: {px(4)} {px(10)}; }}
.lane-dot {{ border-radius: {px(5)}; }}
.divider {{ background-color: {BORDER}; min-height: 1px; }}
.dimmed {{ opacity: 0.6; }}
.ledger-counts {{ padding: {px(4)}; }}
.ledger-group {{ border-radius: {px(6)}; padding: {px(4)} 0; min-height: {px(48)}; }}
.ledger-group.selected.tint-green {{ background-color: alpha({GREEN}, 0.15); }}
.ledger-group.selected.tint-amber {{ background-color: alpha({AMBER}, 0.15); }}
.ledger-group.selected.tint-red {{ background-color: alpha({RED}, 0.15); }}
.ledger-group.selected.tint-muted {{ background-color: alpha({TEXT_MUTED}, 0.15); }}
.tonal-box {{ background-color: {SURFACE_LIGHT}; border-radius: {px(4)}; padding: {px(8)}; }}
.picker {{ background-color: {SPACE_BLACK}; border: 1px solid {OUTLINE}; border-radius: {px(4)}; padding: 0 {px(14)}; min-height: {px(56)}; box-shadow: none; }}
.picker.error {{ border-color: {RED}; }}
.fab {{ background-color: {SIGNAL_ORANGE}; border: none; border-radius: {px(16)}; min-width: {px(56)}; min-height: {px(56)}; padding: 0; box-shadow: 0 2px 6px alpha(black, 0.4); }}
.fab:hover {{ background-color: {ORANGE_LIGHT}; }}
.tab-chip {{ background: none; border: none; box-shadow: none; border-radius: {px(6)}; padding: 0 {px(12)}; min-height: {px(48)}; }}
.tab-chip label {{ color: {TEXT_MUTED}; font-size: {px(14)}; font-weight: 400; }}
.tab-chip.selected {{ background-color: {SURFACE_LIGHT}; }}
.tab-chip.selected label {{ color: {TEXT_PRIMARY}; font-weight: 600; }}
.tab-chip label.count {{ color: {TEXT_SECONDARY}; background-color: {BORDER}; font-weight: 400; }}
.card-tight {{ padding: {px(8)} {px(4)} {px(4)} {px(12)}; }}
.card-tap {{ padding: {px(12)}; border-radius: {px(8)}; }}
.stats-card {{ padding: {px(10)} {px(12)}; }}
.log-view {{ background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: {px(8)}; padding: {px(8)}; }}
.log-line {{ font-family: "{MONO}", monospace; font-size: {px(11)}; }}
.output-card {{ padding: {px(12)}; }}
.field.multiline {{ padding: {px(8)} {px(14)}; min-height: {px(96)}; }}
.filled.tonal-surface {{ background-color: {SURFACE}; border: 1px solid {BORDER}; }}
.filled.tonal-surface label {{ color: {TEXT_PRIMARY}; }}
.filled.amber-fill {{ background-color: {AMBER}; }}
.filled.red-fill {{ background-color: {RED}; }}
.filled.small-text label {{ font-size: {px(12)}; }}
.mode-chip {{ background-color: {SURFACE}; border: none; border-radius: {px(4)}; padding: {px(4)} {px(8)}; min-height: 0; min-width: 0; color: {TEXT_MUTED}; font-size: {px(12)}; box-shadow: none; }}
.mode-chip.selected {{ background-color: alpha({SIGNAL_ORANGE}, 0.15); color: {SIGNAL_ORANGE}; }}
.mode-chip:disabled {{ opacity: 0.4; }}
.mode-chip label {{ color: inherit; font-size: {px(12)}; }}
.filled.red-fill label {{ color: {SPACE_BLACK}; }}
.outlined.red-outline {{ border-color: alpha({RED}, 0.6); }}
.outlined.red-outline label {{ color: {RED}; }}
.dot {{ border-radius: {px(4)}; min-width: {px(8)}; min-height: {px(8)}; }}
.dot-small {{ border-radius: {px(3)}; min-width: {px(6)}; min-height: {px(6)}; }}
.segments {{ background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: {px(8)}; padding: {px(3)}; min-height: {px(30)}; }}
.segment {{ background: none; border: none; box-shadow: none; border-radius: {px(6)}; padding: 0; min-height: {px(28)}; font-family: "{MONO}", monospace; font-size: {px(14)}; font-weight: 500; color: {TEXT_MUTED}; }}
.segment.on {{ background-color: alpha({IRIDIUM}, 0.22); color: {IRIDIUM}; }}
.preset {{ background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: {px(8)}; padding: {px(8)} 0; box-shadow: none; }}
.preset label {{ color: {TEXT_SECONDARY}; }}
.preset label.label-small {{ color: {TEXT_MUTED}; }}
.preset.on {{ background-color: alpha({IRIDIUM}, 0.18); border-color: alpha({IRIDIUM}, 0.5); }}
.preset.on label {{ color: {IRIDIUM}; }}
.chart-card {{ padding: {px(8)} {px(6)}; }}
.pass-banner {{ border-radius: {px(12)}; padding: {px(16)}; }}
.pass-banner-iridium {{ background-color: alpha({IRIDIUM}, 0.05); border: 1px solid alpha({IRIDIUM}, 0.2); }}
.pass-banner-green {{ background-color: alpha({GREEN}, 0.05); border: 1px solid alpha({GREEN}, 0.2); }}
.pass-row {{ background-color: alpha({SURFACE}, 0.5); border-radius: {px(8)}; padding: {px(10)} {px(12)}; }}
.pass-row.active {{ background-color: alpha({IRIDIUM}, 0.1); border: 1px solid alpha({IRIDIUM}, 0.2); }}
.pass-row.past {{ opacity: 0.4; }}
.label-small {{ font-size: {px(11)}; font-weight: 500; }}
.dot-green {{ background-color: {GREEN}; }}
.dot-amber {{ background-color: {AMBER}; }}
.dot-red {{ background-color: {RED}; }}
.dot-muted {{ background-color: {TEXT_MUTED}; }}
.marker-me {{ background-color: {SIGNAL_ORANGE}; border: 2px solid {SPACE_BLACK}; border-radius: {px(9)}; min-width: {px(18)}; min-height: {px(18)}; }}
.marker-label {{ background-color: alpha({SPACE_BLACK}, 0.75); color: {TEXT_PRIMARY}; border-radius: {px(4)}; padding: {px(2)} {px(6)}; font-size: {px(12)}; }}
.map-frame {{ background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: {px(8)}; }}
.map-credit {{ background-color: alpha({SPACE_BLACK}, 0.7); color: {TEXT_SECONDARY}; border-radius: {px(4)}; padding: {px(2)} {px(6)}; font-size: {px(12)}; }}
.panel-bar {{ min-height: {px(56)}; padding: 0 {px(12)}; }}
.map-page {{ padding: {px(16)}; }}
.map-box {{ background-color: {SPACE_BLACK}; }}
.map-note {{ background-color: alpha({SPACE_BLACK}, 0.85); color: {TEXT_PRIMARY}; border-radius: {px(4)}; padding: {px(4)} {px(8)}; font-size: {px(12)}; }}
.map-bubble {{ padding: {px(4)} {px(6)}; }}
.layer-dot {{ border-radius: {px(5)}; min-width: {px(10)}; min-height: {px(10)}; }}
.panel-heading {{ padding: {px(12)} {px(12)} {px(4)} {px(12)}; }}
.panel-heading-row {{ padding: 0 {px(4)} 0 {px(12)}; }}
.panel-item {{ padding: {px(8)} {px(12)}; }}
.check-row.layer-row {{ min-height: {px(48)}; padding: 0 {px(12)}; }}
.node-row {{ min-height: {px(56)}; padding-left: {px(12)}; }}
.node-row .check-row {{ padding: 0 {px(12)} 0 0; }}
.zones-map {{ margin: {px(12)} {px(16)} 0 {px(16)}; }}
.zone-row {{ min-height: {px(64)}; padding-left: {px(12)}; }}
.zone-texts {{ padding: {px(8)} 0; }}
.alert-row {{ min-height: {px(40)}; }}
.radio-row {{ min-height: {px(48)}; }}
.filled.tall, .textbutton.tall, .outlined.tall {{ min-height: {px(48)}; }}
.world-box {{ border: 1px solid {BORDER}; border-radius: {px(6)}; padding: {px(12)}; }}
.map-row {{ border: 1px solid {BORDER}; border-radius: {px(6)}; padding-left: {px(12)}; }}
.map-row.active {{ background-color: alpha({SIGNAL_ORANGE}, 0.10); border-color: alpha({SIGNAL_ORANGE}, 0.4); }}
.map-row > button.flat {{ padding: {px(10)} 0; }}
.map-row > button.flat:hover {{ background: none; }}
.node-sheet {{ padding: {px(8)} {px(24)} {px(24)} {px(24)}; }}
.card.card-pad.cards-section {{ padding: {px(16)}; }}
.card-row {{ padding-top: {px(12)}; }}
.card-fingerprint {{ margin: {px(8)} 0; }}
.my-card-fingerprint {{ font-size: {px(18)}; font-weight: 500; margin-top: {px(12)}; }}
.scanner-view {{ background-color: black; border-radius: {px(8)}; }}
.subheader {{ min-height: {px(56)}; border-bottom: 1px solid {BORDER}; padding: 0 {px(4)}; }}
.subheader.plain {{ min-height: {px(48)}; border-bottom: none; padding: 0; }}
.compose {{ padding: {px(8)}; }}
.field.compose-field {{ border-color: {BORDER}; }}
.field.compose-field:focus-within {{ border: 2px solid {TEXT_SECONDARY}; }}
.field.compose-field text placeholder {{ font-size: {px(14)}; }}
.group-title {{ font-size: {px(14)}; font-weight: 500; color: {TEXT_SECONDARY}; padding: {px(20)} {px(16)} {px(4)} {px(16)}; }}
.nav-row {{ min-height: {px(64)}; padding: {px(8)} {px(16)}; }}
.kv-key {{ color: {TEXT_SECONDARY}; font-size: {px(14)}; }}
.kv-value {{ color: {TEXT_PRIMARY}; font-size: {px(14)}; }}
.dialog {{ background-color: {SURFACE_HIGH}; border: 1px solid {BORDER}; border-radius: {px(16)}; padding: {px(24)}; }}
.dialog-title {{ font-size: {px(20)}; font-weight: 600; }}
.field.error {{ border-color: {RED}; }}
.switch-row {{ min-height: {px(56)}; }}
.check-row {{ padding: {px(8)} 0; }}
.check {{ border: 2px solid {TEXT_MUTED}; border-radius: {px(3)}; min-width: {px(18)}; min-height: {px(18)}; }}
.check.on {{ border-color: {SIGNAL_ORANGE}; background-color: {SIGNAL_ORANGE}; }}
.pick-row {{ padding: {px(10)} {px(4)}; border-radius: {px(8)}; }}
.radio {{ border: 2px solid {TEXT_MUTED}; border-radius: {px(10)}; min-width: {px(16)}; min-height: {px(16)}; }}
.radio.on {{ border-color: {SIGNAL_ORANGE}; background: radial-gradient(circle, {SIGNAL_ORANGE} 0%, {SIGNAL_ORANGE} 45%, transparent 50%); }}
.hold {{ background: none; border: 2px solid {SIGNAL_ORANGE}; border-radius: {px(12)}; padding: 0; box-shadow: none; min-height: {px(64)}; }}
.hold.danger {{ border-color: {RED}; }}
.timeout-row {{ border-radius: {px(4)}; padding: {px(8)} {px(12)}; }}
.timeout-row.selected {{ background-color: alpha({GREEN}, 0.15); }}
.contact-row {{ background-color: {SURFACE_LIGHT}; border-radius: {px(6)}; padding-left: {px(12)}; }}
.status-banner {{ border-radius: {px(8)}; padding: {px(10)} {px(12)}; }}
.status-banner.amber {{ background-color: alpha({AMBER}, 0.12); border: 1px solid alpha({AMBER}, 0.4); }}
.status-banner.red {{ background-color: {ERROR_CONTAINER}; border: 1px solid alpha({RED}, 0.4); }}
.status-banner.green {{ background-color: alpha({GREEN}, 0.10); border: 1px solid alpha({GREEN}, 0.35); }}
.status-banner.muted {{ background-color: {SURFACE}; border: 1px solid {BORDER}; }}
alertdialog, dialog {{ background-color: {SURFACE_HIGH}; color: {TEXT_PRIMARY}; }}
alertdialog .heading, alertdialog .title {{ color: {TEXT_PRIMARY}; font-size: {px(20)}; font-weight: 600; }}
alertdialog .body {{ color: {TEXT_SECONDARY}; font-size: {px(14)}; }}
alertdialog button {{ background: none; border: none; box-shadow: none; color: {SIGNAL_ORANGE}; font-weight: 500; }}
alertdialog button.destructive-action {{ color: {RED}; }}
scrolledwindow, viewport {{ background: none; }}
scrollbar {{ background: none; }}
scrollbar slider {{ background-color: {SURFACE_LIGHT}; min-width: {px(4)}; border-radius: {px(4)}; }}
switch {{ background-color: {SURFACE_LIGHT}; border: 2px solid {TEXT_MUTED}; min-width: {px(52)}; min-height: {px(32)}; border-radius: {px(16)}; }}
switch:checked {{ background-color: {SIGNAL_ORANGE}; border-color: {SIGNAL_ORANGE}; }}
switch slider {{ background-color: {TEXT_MUTED}; min-width: {px(16)}; min-height: {px(16)}; margin: {px(6)}; border-radius: {px(8)}; box-shadow: none; }}
switch:checked slider {{ background-color: {SPACE_BLACK}; min-width: {px(24)}; min-height: {px(24)}; margin: {px(2)}; border-radius: {px(12)}; }}
checkbutton radio, checkbutton check {{ background: none; border: 2px solid {TEXT_MUTED}; min-width: {px(16)}; min-height: {px(16)}; border-radius: {px(10)}; -gtk-icon-source: none; }}
checkbutton check {{ border-radius: {px(3)}; }}
checkbutton radio:checked {{ border-color: {SIGNAL_ORANGE}; background: radial-gradient(circle, {SIGNAL_ORANGE} 0%, {SIGNAL_ORANGE} 45%, transparent 50%); }}
checkbutton check:checked {{ border-color: {SIGNAL_ORANGE}; background-color: {SIGNAL_ORANGE}; }}
popover > contents {{ background-color: {SURFACE_HIGH}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER}; border-radius: {px(8)}; }}
{colours}
"""


_provider = None


def apply(display: Gdk.Display | None = None) -> None:
    """The stylesheet for the display, and the app's icons (a hicolor tree beside this file,
    also installed system-wide by the package) on the icon theme's path."""
    global _provider
    display = display or Gdk.Display.get_default()
    if _provider is not None:
        Gtk.StyleContext.remove_provider_for_display(display, _provider)
    _provider = Gtk.CssProvider()
    _provider.load_from_string(css())
    Gtk.StyleContext.add_provider_for_display(display, _provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    icons = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
    theme = Gtk.IconTheme.get_for_display(display)
    if icons not in theme.get_search_path():
        theme.add_search_path(icons)
