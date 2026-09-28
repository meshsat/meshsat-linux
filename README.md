<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/mark-dark.png">
  <img src="docs/images/mark-light.png" alt="MeshSat" width="190">
</picture>

### MeshSat for Linux phones: the LoRa back cover as a node, the Bridge in your pocket, one package.

[![License: GPL v3](https://img.shields.io/badge/license-GPLv3-blue)](LICENSE)
![Mobian / Debian 13, arm64](https://img.shields.io/badge/platform-Mobian%20%2F%20Debian%2013%20arm64-555)

[Install](docs/INSTALL.md) ·
[The node](https://github.com/meshsat/meshsat-lora-backplate) ·
[The Bridge](https://github.com/meshsat/meshsat) ·
[What is proven](#what-is-proven-and-what-is-not) ·
[meshsat.net](https://meshsat.net)

</div>

A PinePhone with the Pine64 LoRa back cover can be a Meshtastic node by itself, and with the MeshSat Bridge running beside the node it becomes a router between the LoRa mesh, a satellite modem on USB-C and the MeshSat Hub. This repository packages all of it for Linux phones: one `.deb`, installed with one command, and the MeshSat app in the phone's app grid, the same screens as MeshSat Android and iOS.

> **Status: pre-release.** This is a prototype under active development, not a finished product. The node and the Bridge are proven on one phone on one bench, at **0 dBm only**: the back cover's radio runs on a plain crystal that drifts as the amplifier heats, so long frames fail from 5 dBm up and the phone cannot receive for some seconds after each transmission. A radio that stops answering has to be re-seated by hand. The package has never been installed by anyone but its authors and has never been used in an actual emergency. See [What is proven, and what is not](#what-is-proven-and-what-is-not) before you rely on it for anything.

## How it fits together

```mermaid
flowchart LR
    mesh["Meshtastic mesh<br/>LoRa 868 MHz"] <--> radio
    subgraph phone["PinePhone, Mobian"]
        radio["SX1262 in the back cover"] <-->|"I2C pogo pins"| daemon["meshtasticd<br/>+ MeshSat bridge layer"]
        daemon <-->|"TCP 4403"| bridge["MeshSat Bridge"]
        bridge <--> app["MeshSat app<br/>GTK4, libadwaita"]
        bridge <-->|"USB-C"| rb["RockBLOCK 9603"]
    end
    rb <-->|"Iridium SBD"| sat(("Iridium"))
    sat <--> hub["MeshSat Hub"]
    bridge <-->|"Wi-Fi, cellular"| hub
```

## What is here

- [`docs/INSTALL.md`](docs/INSTALL.md): the one command, the optional Hub key and satellite modem, what the node does and does not do.
- `app/meshsat/`: the MeshSat app, Python with GTK 4 and libadwaita: the screens of [MeshSat Android](https://github.com/meshsat/meshsat-android) and [iOS](https://github.com/meshsat/meshsat-ios) (Home, Messages, Map, People, Setup and its pages) drawn natively for a phone in the hand, with the same colour tokens, type (IBM Plex), Material icons, words and measures (written in the Android app's dp and scaled once, 1 dp = 0.9 px on a 360 px screen; `MESHSAT_APP_SCALE` changes it), night mode as the same red-only colour matrix over the whole window, and the map on OpenStreetMap tiles through the Android app's dark-tile matrix (libshumate); satellite passes are the Bridge's predictions for the phone's position (geoclue, the node, or a position typed in) drawn as the Android chart. It reads the Bridge's API on `127.0.0.1:6050` and never opens the node's own port. Its tabs and pages open over D-Bus (`gapplication action net.meshsat.Bridge tab "'map'"`, `open "'satellite'"`, `night`), which is how `tools/capture-phone.sh` takes the parity captures. The icon in the app grid, the `.desktop` entry and the AppStream metadata are under `package/`.
- `package/`: the Debian package's control files, maintainer scripts and static files; `build-deb.sh` assembles the package from the node sources of [meshsat-lora-backplate](https://github.com/meshsat/meshsat-lora-backplate) at a pinned commit, a daemon built on a phone from [meshsat-firmware](https://github.com/meshsat/meshsat-firmware), the Bridge out of [meshsat](https://github.com/meshsat/meshsat)'s container image (`fetch-bridge.sh`), and Meshtastic's web client release. No gateway logic lives here.
- `tools/`: `capture-phone.sh` (the captures above) and `vector2svg.py` (Android vector drawables to the SVG icons the app ships).
- The package's units: `meshtasticd.service` (the node), `meshsat-radio-watch.timer` (the watchdog that tells a user to re-seat a cover whose radio stopped answering, and starts the node again when it answers), `meshsat-bridge.service` (the Bridge, over TCP to the node).

## What is proven, and what is not

| | State |
|---|---|
| The package installs with one command on a Mobian PinePhone Pro and starts the node, the watchdog and the Bridge | **Yes**, 28 Sep 2026: `sudo apt install ./meshsat_0.2.0_arm64.deb`, exit 0, the three units active, `Final Tx power: 0 dBm`, the node's identity carried over; every upgrade since 0.1.0 too |
| The MeshSat icon in the app grid opens the app, with the Android and iOS apps' screens | **Yes**, 28 Sep 2026: the owner used the first native build on the bench phone and had its scale, icon and map corrected the same day; 0.2.0's captures of every screen are in the release notes |
| Messages typed in the app reach a T-Deck, and a T-Deck's texts show in the app | **Yes** for the Bridge underneath (28 Sep 2026, over its API); the app's composer sends through the same call, **not yet exercised by a person** |
| The node: texts both ways with a T-Deck at 0 dBm | **Yes**, 28 Sep 2026, on the bench of meshsat-lora-backplate |
| The Bridge talks to the node over TCP | **Yes**, on the phone, 28 Sep 2026: a text sent through the Bridge's API was read on a T-Deck (`Received text msg from=0x52cb81e7`), and a text typed on the T-Deck reached the Bridge's message store through the daemon |
| A text from the mesh reaches the Hub through the phone | **Not yet**: needs a Hub API key on the phone |
| A text from the mesh reaches the satellite through the phone | **Not yet**: needs the RockBLOCK on USB-C |
| Transmit above 0 dBm | **No**, a hardware limit of the back cover until its crystal is replaced by a TCXO |
| Use without a person nearby | **Not possible** as long as only a hand can reset a radio that stopped answering |
| Published in an app store or an apt repository | **No**, not before a text has gone from the phone to the satellite |
| Deployment to a real end user, use in an actual emergency | **Never** |

## Related projects

- **[meshsat-lora-backplate](https://github.com/meshsat/meshsat-lora-backplate)**, the back cover as a Meshtastic node: the bridge layer, the measurements, the node packaging this package vendors
- **[MeshSat Bridge](https://github.com/meshsat/meshsat)**, the gateway software this package runs on the phone
- **[MeshSat Android](https://github.com/meshsat/meshsat-android)** and **[MeshSat iOS](https://github.com/meshsat/meshsat-ios)**, the same idea on phones that are not Linux
- **[MeshSat Hub](https://hub.meshsat.net)**, where the messages end up

## Licence

GPL-3.0, like the rest of MeshSat. Meshtastic is a registered trademark of Meshtastic LLC; this project is not affiliated with it.
