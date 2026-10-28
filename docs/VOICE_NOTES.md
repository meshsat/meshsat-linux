# Voice notes and photos (MESHSAT-1735)

The Linux half, mirrored from MeshSat Android's `docs/VOICE_NOTES.md` screen for screen. The
wire is the Bridge's `docs/LXMF_ATTACHMENTS.md` (meshsat repo): nothing MeshSat-specific is on
it, a note from Sideband or MeshChat plays here and one from here plays there. On Linux the
Bridge on the phone holds the bytes (`lxmf_attachments`, 16 MiB) and this app reads them over
its API; Android keeps them in its own Room table.

## What travels

| LXMF field | Value | This app writes | This app reads |
|---|---|---|---|
| `FIELD_AUDIO` (0x07) | `[mode, bytes]` | mode 0x10 (Opus OGG): a whole RFC 7845 Ogg Opus file, mono, 48 kHz, 16 kbit/s ceiling, written by GStreamer (`opusenc ! oggmux`), what Sideband records | any Opus mode 0x10-0x19 plays (GStreamer `playbin` on the file written under `$XDG_RUNTIME_DIR`); a Codec2 mode 0x03-0x09 plays when `pycodec2` is importable (the packed frames at the mode's frame size, decoded to 8 kHz 16-bit mono and played as a WAV), else is kept and shown as "Voice note (Codec2 700C), 7 KB" with "Playback of Codec2 700C is not supported on this phone."; 450 and 450PWB (0x01, 0x02) are never decoded, as in every client |
| `FIELD_IMAGE` (0x06) | `[format, bytes]` | `"webp"`, the picked photo scaled to a 640 px long edge and compressed until it fits (GdkPixbuf's WebP saver when `webp-pixbuf-loader` is installed, else Pillow) | any format GdkPixbuf or Pillow decodes, shown inline; another is named with its size |

Caps, as the Bridge applies them: one audio and one image per message, together at most
**64 KiB** (`attachments.MAX_BYTES`); a note is at most **30 s** (`attachments.MAX_NOTE_MS`, the
recorder stops itself there). The code is `app/meshsat/model/attachments.py` (the policy, the
mode names, the Codec2 frame table, an Ogg Opus reader and writer), `media.py` (the cache),
`playback.py` (GStreamer, pycodec2, GdkPixbuf), `voicenotes.py` (the widgets).

## The Reticulum lane

The app had no Reticulum conversation before this: it has one now, as Android's (`Peers.kt`,
MESHSAT-1553), as small as the parity allows. A chat is keyed `lxmf:<hash>` (what the Bridge
files an LXMF message's ends as), named as the peer announced itself (`GET /api/lxmf/peers`)
else "Reticulum" and the first eight characters of the address, "By Reticulum (LXMF), <hash>"
under the name, the "Reticulum" filter chip, the "LXMF" badge on a bubble, "Message by
Reticulum" in the box, and Android's three lines under it. New message lists the peers the node
has heard ("By Reticulum, <16 characters>... N hops away") and takes an address typed or
pasted ("Message this address"). A send is `POST /api/lxmf/send`; the row shows at once from
this app's own record (the sent log, as the mesh and SMS lanes do) and gives way to the Bridge's
own row once its worker has filed it (`chat.merge_lxmf`).

## Policy: Reticulum links only

`attachments.carries(transport)` is true for `lxmf` only; `note()`, `can_send()` and `fits()`
are Android's `AttachmentPolicy` word for word, unit-tested. **One difference:** Android shows the
microphone and the photo button on every chat and refuses with the amber line ("By SMS only
the text goes: a voice note 12 s, 18 KB travels by Reticulum alone, so it is not sent.") when the
bearer cannot carry them; here the two buttons are shown on a Reticulum chat only, so a note
cannot be made where it could not go. The amber line is still in the model, for the day another
bearer carries one.

## UI (Messages, one conversation)

- **Composer row** on a Reticulum chat: microphone, photo, text box, send. The microphone
  **records while held** (`voicenotes.RecordButton`; red at 25 % while recording, "Recording,
  4.2 s" as its name); lifting the finger ends the note, 30 s ends it by itself; a press that
  recorded nothing says "Hold the microphone while you speak."; a note over the cap "Too long for
  one message (68 KB); keep it shorter.". With a screen reader, or in the tests, where holding is
  awkward, a click starts and a second click stops, as Android's click action with TalkBack.
  `MESHSAT_APP_AUDIO_SOURCE` replaces the microphone with any GStreamer source (the tests:
  `audiotestsrc`). No permission is asked (Linux asks none); a microphone that cannot be opened
  says so. Where GStreamer has no Opus encoder: "Voice notes need GStreamer's Opus encoder on this
  device." (Android's line is about Android 10).
- **Pending attachments**: a row per item above the box, "Voice note, 4.2 s, 7 KB" with play/stop
  and "Photo, 3 KB" with a 32 dp thumbnail, each with a remove cross; one of each at most (the
  buttons disable); the photo's byte budget is the cap minus the note.
- **Transcript**: none. Linux phones have no platform speech recogniser; the "Heard: ..." proposal
  with "Use as text" and "Discard" is not ported (ledger `chat.attachments.transcript`, excluded).
- **Hint lines**: the policy line above the bearer's own line, as Android.
- **Bubbles**: a voice note is a card with play/stop and "Voice note, 4.2 s, 7 KB" (the length of an
  Opus note is read from its Ogg pages, so the bytes are fetched on view, one GET per note, kept);
  a Codec2 note this phone cannot decode is the same card without a button, the "playback not
  supported" line and, this edition's own, "Save a copy" of the bytes; a photo is shown inline,
  full bubble width, at most 320 dp tall. A text-less message shows the card alone. One note plays
  at a time (`playback.PLAYER`).
- **Lazy**: a Reticulum message's attachments are asked of the Bridge once per message
  (`GET /api/lxmf/messages/{id}/attachments`) and kept, an empty list and a 404 too; the bytes on
  the first play or view, kept up to 8 MiB.
- **The method chips** (Direct, Auto, Opportunistic, Propagated): not here. The Bridge's
  `POST /api/lxmf/send` takes no method; the Bridge's router sends direct as a resource.

## Notifier

`meshsat-notify` says "Reticulum: <name or the address's first eight characters>" with the text,
or "Voice note" / "Photo" / "Photo and Voice note" when the text is empty, as Android's
notification. No event of the Bridge announces an LXMF message, so the notifier reads the newest
twenty messages every poll (one more GET) and tells about the Reticulum rows above its watermark
(`outside.new_reticulum_rows`); a text-less row is named from the Bridge's attachment list.

## Tests

- On the runner (`python3 -m unittest discover tests`, no GTK needed): `test_attachments.py` (the
  policy, the sizes and seconds as Kotlin formats them, the mode names, the Codec2 frame table,
  Ogg Opus written and read back, the send body), `test_lxmf_words.py` (the lane, the names, the
  composer's lines, the New message rows, the merge of a send), `test_media.py` (the cache and
  the fake Bridge's `/api/lxmf/send` and attachment routes, a picture shrunk through Pillow),
  `test_outside.py` (the notification's words and the watermark).
- On the phone (`tests/e2e/cases/h_voice.py`, scenario `lxmf`, `MESHSAT_APP_AUDIO_SOURCE=
  audiotestsrc`): the buttons on a Reticulum chat and not on a mesh chat, the cards of a received
  note, Codec2 note and photo, a note recorded through the test source and sent in the body, a
  photo picked and sent as WebP, New message's peers and address. **Not yet run**: the phone was
  not available for this release; the ledger rows stay `built` until they are.

## Not done

- No speech transcript (no recogniser on Linux phones).
- A Codec2 note plays only where `pycodec2` is installed (`pip install pycodec2`, needs
  libcodec2); the package does not depend on it. Nothing records Codec2.
- The conversation list previews a text-less note as an empty line, as Android.
- Attachments do not go through the access rules or any other bearer, as on the Bridge.
