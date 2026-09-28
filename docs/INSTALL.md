# Install MeshSat on a Linux phone

For a Linux phone running Mobian (Debian 13, arm64): a PinePhone or PinePhone Pro with the Pine64 LoRa back cover, or any phone with a Meshtastic node in Bluetooth range. One package, one command.

## One command

Download the package from the [releases](https://github.com/meshsat/meshsat-linux/releases) (the release page lists its sha256), then, on the phone:

```
wget https://github.com/meshsat/meshsat-linux/releases/download/v0.7.0/meshsat_0.7.0_arm64.deb
sudo apt install ./meshsat_0.7.0_arm64.deb
```

That is all. The package installs the Meshtastic daemon for the back cover, its configuration (0 dBm, the one power the radio is qualified at), Meshtastic's web client, the radio watchdog, the MeshSat Bridge and the MeshSat app, and starts the services. The **MeshSat** icon is in the app grid; tap it and the app opens: the same screens as MeshSat Android and iOS, Home, Messages, Map, People and Setup, with this phone's node, a satellite modem on USB-C and the MeshSat Hub. The moon on Home is night mode. A banner at the top says when the Bridge or the node cannot be reached, and what to do.

## With the LoRa back cover, or with a node over Bluetooth

When the phone boots, the package looks for the Pine64 LoRa back cover on the pogo pins (`meshsat-hardware`). With one, this phone is the node: the daemon drives the cover and the Bridge talks to it. Without one, the daemon stays off and the Bridge starts in Bluetooth mode, as MeshSat Android and iOS work: open the app, go to Setup > Your MeshSat node, tap **Scan for Meshtastic devices**, pick your node under **Found devices**, and enter the PIN the node shows on its screen. From then on the phone reconnects to that node by itself, across restarts. **Disconnect** leaves the node; **Forget this node** also drops the pairing. A phone with a cover that should use a node over Bluetooth anyway says so in `/etc/meshsat/hardware.conf` with `MESHSAT_NODE=bluetooth`; **Look for a LoRa back cover again** on the same page asks the phone to decide again (a cover put on, or taken off).

## Outside the app: notifications and the satellite signal

A small service of your session (`meshsat-notify`, started with the phone's shell) tells you what MeshSat Android tells you, whether the app is open or not: a text that arrived ("Mesh: !a1b3c2ec"), a message that did not go, an SOS in progress with its **Cancel SOS** button, and, while a satellite modem is connected, the signal as one notification kept up to date ("Iridium signal 3/5"). On Phosh (Mobian's shell) the package also adds a **MeshSat tile** to the quick settings (pull the top bar down: the satellite's bars, or the mesh and its node count; a tap opens the app) and a **widget on the lock screen**; both appear at the next start of the shell after the install, and Phosh's own settings (Mobile Settings > Quick Settings, Lock Screen) take them out again. Phosh's top bar itself takes no icons from applications, so the always-visible icon MeshSat Android has is not possible there. On Plasma Mobile and on desktops the same service shows a tray icon with the bars.

A node that was already run on this phone by hand keeps its identity: the package copies the keys and channels it finds under `~/.portduino/default/prefs`.

## A new node: its channels

A node installed fresh has a region and no channel. Put a Meshtastic channel URL (from the Meshtastic app's share dialog; it carries the keys, keep it out of chat logs) in a file, then:

```
cat channel-url.txt | meshsat-node-channels --owner my-phone --short MYPH --role CLIENT_MUTE
```

The first run makes a private Python environment for the Meshtastic client library (needs the network once).

## Three optional steps

- **SMS.** With a SIM in the phone, texts go out and come in through it, as on MeshSat Android: the SMS lane on Home, SMS chats under Messages, and the emergency contacts under Setup > Safety, who get an SOS by SMS with your position and a map link. The Bridge reaches the modem through ModemManager (the package installs the polkit rule for that); nothing to set up beyond the SIM, and `MESHSAT_SIM_PIN=` in `/etc/meshsat/bridge.env` if it has a PIN. Your carrier's normal rates apply.
- **The MeshSat Hub.** Setup > Hub in the app takes the Hub's QR code text, or put an API key from your tenant's Fleet page at [hub.meshsat.net](https://hub.meshsat.net) into `/etc/meshsat/bridge.env` (`HUB_API_KEY=`), then `sudo systemctl restart meshsat-bridge`. Without it the mesh works and the Hub is simply not reached.
- **The satellite.** A RockBLOCK 9603 on USB-C (through a USB-C to USB-A adapter) is found by the Bridge by itself; `MESHSAT_IRIDIUM_PORT=` in the same file pins its port if you want. Setup > Satellite shows the modem and its signal; Satellite passes predicts when a satellite is overhead for your position, which comes from the phone's location service (Settings > Privacy > Location Services, then allow MeshSat), from the node, or from a position you type in there (the node then carries it as its fixed position).

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
