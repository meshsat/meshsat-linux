# Install MeshSat on a Linux phone

For a PinePhone or PinePhone Pro with the Pine64 LoRa back cover, running Mobian (Debian 13, arm64). One package, one command.

## One command

Download the package from the [releases](https://github.com/meshsat/meshsat-linux/releases) (the release page lists its sha256), then, on the phone:

```
wget https://github.com/meshsat/meshsat-linux/releases/download/v0.2.0/meshsat_0.2.0_arm64.deb
sudo apt install ./meshsat_0.2.0_arm64.deb
```

That is all. The package installs the Meshtastic daemon for the back cover, its configuration (0 dBm, the one power the radio is qualified at), Meshtastic's web client, the radio watchdog, the MeshSat Bridge and the MeshSat app, and starts the services. The **MeshSat** icon is in the app grid; tap it and the app opens: the same screens as MeshSat Android and iOS, Home, Messages, Map, People and Setup, with this phone's node, a satellite modem on USB-C and the MeshSat Hub. The moon on Home is night mode. A banner at the top says when the Bridge or the node cannot be reached, and what to do.

A node that was already run on this phone by hand keeps its identity: the package copies the keys and channels it finds under `~/.portduino/default/prefs`.

## A new node: its channels

A node installed fresh has a region and no channel. Put a Meshtastic channel URL (from the Meshtastic app's share dialog; it carries the keys, keep it out of chat logs) in a file, then:

```
cat channel-url.txt | meshsat-node-channels --owner my-phone --short MYPH --role CLIENT_MUTE
```

The first run makes a private Python environment for the Meshtastic client library (needs the network once).

## Two optional steps

- **The MeshSat Hub.** Setup > Hub in the app takes the Hub's QR code text, or put an API key from your tenant's Fleet page at [hub.meshsat.net](https://hub.meshsat.net) into `/etc/meshsat/bridge.env` (`HUB_API_KEY=`), then `sudo systemctl restart meshsat-bridge`. Without it the mesh works and the Hub is simply not reached.
- **The satellite.** A RockBLOCK 9603 on USB-C (through a USB-C to USB-A adapter) is found by the Bridge by itself; `MESHSAT_IRIDIUM_PORT=` in the same file pins its port if you want. Setup > Satellite shows the modem and its signal.

## What you get, and what you do not

| | |
|---|---|
| Receives | Everything on its channels, at any length. |
| Sends | At 0 dBm, 1 mW: a house or a street, not the kilometres of a real node. Above that the radio's plain crystal drifts and long frames arrive damaged; the cap is `SX126X_MAX_POWER` in `/etc/meshtasticd/config.d/lora-pinedio-backcover.yaml`. |
| After sending | Deaf for 5 to 28 seconds, so every broadcast goes out three times and the ack of a direct message is usually missed. |
| Direct messages | To nodes whose announcement the phone has heard. |
| A radio that stops answering | Only a hand resets it: take the cover off and press it back on until it clicks. The app's banner and `journalctl -u meshsat-radio-watch` say so; the node starts again by itself once the radio answers. |
| The map | OpenStreetMap tiles when there is internet, in the dark look of the other MeshSat apps; no offline maps yet. |

The measurements behind every line: [meshsat-lora-backplate](https://github.com/meshsat/meshsat-lora-backplate), `docs/BACKPLATE.md` and `docs/data/`.

## Where things are

| | |
|---|---|
| `meshsat-app` | the app (also in the app grid): Home, Messages, Map, People, Setup |
| `http://localhost:6050/` | the Bridge's own console, in any browser (the expert pages under Setup > Advanced open it inside the app) |
| `https://localhost:9443/` | Meshtastic's own web client, served by the daemon with the package's self-signed certificate (accept it once; desktop layout) |
| `/etc/meshsat/bridge.env` | the Bridge's settings (Hub key, ports) |
| `/etc/meshtasticd/` | the daemon's configuration |
| `/var/lib/meshtasticd/.portduino/default/prefs` | the node's keys, channels and node database |
| `/var/lib/meshsat/meshsat.db` | the Bridge's database |
| `~/.config/meshsat/app.json` | the app's own settings (night mode) |
| `journalctl -u meshtasticd`, `-u meshsat-bridge`, `-u meshsat-radio-watch` | the logs |
| `/usr/share/doc/meshsat/PROVENANCE` | what the package was built from |

## Remove

`sudo apt remove meshsat` stops the services and keeps the configuration, the node's identity and the Bridge's database. `sudo apt purge meshsat` removes those too.

## Build the package yourself

`build-deb.sh` in this repository assembles the package from the node sources of meshsat-lora-backplate at a pinned commit, a daemon built on a phone (`packaging/build-daemon.sh` there), the Bridge out of its container image (`fetch-bridge.sh`) and Meshtastic's web client release; the header of the script lists the inputs and their checksums.
