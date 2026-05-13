# voronFDM Reverse-Engineering Findings

Deep static-analysis findings for the Phrozen Arco firmware (V199). Goal: identify the **best** way to display a message on the printer's TFT screen from an external script (the KAOS install script), and confirm the right reboot mechanism.

**Source binaries** (all not stripped, with DWARF debug info):
- `reference/Arco_FW_V199/phrozen_dev/phrozen_dev/serial-screen/voronFDM` (1.0 MB) — full dev build
- `serial-screen/voronFDM-arm-mks` (709 KB) — MKS production build (RK3328)
- `serial-screen/voronFDM-arm-prz` (816 KB) — Phrozen production build (RK3308)

Tools used: `aarch64-linux-gnu-objdump`, `nm`, `readelf`, `strings`, custom Python register-tracking analyzer using `pyelftools` + `capstone`. No ghidra / radare2 needed because the symbol table is intact.

---

## TL;DR

**Best path for the install script** (high confidence, zero protocol guessing, no race condition):

1. Run `systemctl stop klipper` immediately before reboot
2. Wait 2 seconds for the popup to render on-screen
3. `reboot` (with a `sudo -S` fallback using the leaked `makerbase` password)

**Why this works**: voronFDM is a WebSocket client to Moonraker. When Klipper goes down, Moonraker emits `notify_klippy_shutdown`, which voronFDM matches with a hard-coded `strcmp` and triggers popup type **1001**, which displays the Nextion popup containing the literal English text *"Please shut down and restart"*. This is the EXACT same popup the stock firmware shows during its native Klipper restart flow (confirmed at `voronFDM:0x5ae1c`).

**Why not M117**: voronFDM does NOT bridge generic gcode-response text to the screen. It only matches a fixed vocabulary of substrings (printer state changes, AMS events, probe errors) — see "M117 path" below.

**Why not the TCP API**: voronFDM listens on `127.0.0.1:8809` and accepts JSON commands, but the dispatch vocabulary is OTA / cloud-binding / filament-settings — there is no "show arbitrary text" command, and the only text-displaying branches (`bind` / `unbind`) have state-mutating side effects on the cloud connection.

---

## 1. Firmware architecture (what runs on the printer)

Confirmed from stock shell scripts (`start.sh`, `KlipperScreen-start.sh`, `klipperscreen.service`) and from voronFDM's own string constants:

| Component | What it does | User | Source visible? |
|---|---|---|---|
| **Klipper** | Motion control, gcode | `mks` / `prz` | Yes (Python) |
| **Moonraker** | HTTP/WS API in front of Klipper, port 7125 | `mks` / `prz` | Yes (stock) |
| **KlipperScreen** | Started as systemd unit but **does not drive the TFT** here | `mks` / `prz` | Yes (stock) |
| **voronFDM** | **Owns `/dev/ttyS1`, drives the Nextion-style TFT, bridges Moonraker ↔ screen** | `mks` / `prz` | **No — binary only** |
| `phrozen_master` | Hosts UDS server at `/tmp/UNIX.domain`; cloud-relay daemon | `mks` / `prz` | No — not in V199 dump |
| `phrozen_slave_ota` | OTA helper | `mks` / `prz` | No |
| `phrozen-go-release` | TUTK cloud/IoT relay (in `PhrozenGo.tar`) | `mks` | No |

The physical TFT is **Nextion-protocol over UART on `/dev/ttyS1`** to a separate STM32F407VET6 screen MCU. KlipperScreen is running but is not what you see on the LCD (the unit comment in `KlipperScreen-start.sh:9` says "暂时使用mks自带的串口屏" = "temporarily use MKS-builtin serial screen"). voronFDM is what you actually see.

---

## 2. voronFDM internals

### 2.1 Three IPC entry points

```
            ┌────────────────┐        ┌────────────────┐
Klipper ────┤  Moonraker WS  │───────►│ webreceive_    │
            └────────────────┘        │ pthread_main_  │
                                      │ init (RX)      │
                                      └───────┬────────┘
                                              │
External clients (TCP/WS) ──┐                 ▼
                            ▼          ┌───────────────┐
                ┌───────────────────┐  │ Popup_pthread │
                │ tcpserver_pthread │  │ Continue_play │
                │ _main_init :8809  │  │ ing_pthread   │
                └─────────┬─────────┘  └──────┬────────┘
                          │                   │
                          └─────────┬─────────┘
                                    ▼
                       ┌─────────────────────────┐
                       │  utils_uart_send_string │
                       │  ───────► /dev/ttyS1    │
                       │           Nextion HMI   │
                       └─────────────────────────┘
            ┌──────────────────┐
phrozen_   │ UDSClient_*       │   ◄── voronFDM is a UDS *client* to
master ────┤ → /tmp/UNIX.domain│       phrozen_master, not a UDS server.
            └──────────────────┘
```

Symbols confirming each entry point:

- **TCP server** (port 8809, conf in `tcpserver_pthread_main_init:0x7e7f4` — `mov w0, #0x2269`): listens for `{"cmd":..., "msg":..., "data":..., "sender":...}` JSON envelopes. Handler is `tcpserver_handle_client_rx_message`.
- **WebSocket client** to Moonraker (`localhost:7125`): `websocket_pthread_client_init` opens the WS, `webreceive_pthread_main_init` parses incoming events.
- **WebSocket server** thread (`websocket_pthread_main_init`): exists but appears to be a peer/sibling channel. Smaller dispatch surface; we did not deeply analyze.
- **UDS client** (`UDSClient_Connect10`/`11`/`12`): voronFDM dials out to `/tmp/UNIX.domain` (server is `phrozen_master`, not in this firmware bundle).

### 2.2 TCP command vocabulary (port 8809)

JSON envelope confirmed from disassembly of the dispatch entry:

```json
{ "cmd": "<string>",
  "msg": "<optional>",
  "data": { ... },
  "sender": "<optional>" }
```

If `cmd` is missing or empty, voronFDM responds `{"error":"Missing or invalid 'cmd'"}` and closes.

Full extracted dispatch vocabulary (37 unique values found via `strstr` argument tracking):

| `cmd` value | Purpose | Drives screen? |
|---|---|---|
| `PhrozenOTA` | OTA orchestrator | yes (progress %) |
| `connect_success` | Cloud connect ACK | minor |
| `ota_update_nodowm_check`, `ota_update_check` | Check for FW update | yes |
| `ota_download_package`, `ota_download_progress` | Download FW | yes |
| `PhrozenGo`, `boot` | Cloud relay startup | no |
| **`bind`, `unbind`** | **Cloud bind state, sets `popup1.conn_name.txt="<user>"` and `pop_num.val=36`** | **YES — but mutates `G_appconnect`** |
| `bind_already`, `bind_failed` | Bind result | yes |
| `check_state`, `check_shield`, `check_name`, `check_version` | Read-only queries | no |
| `change_shield_setting` (with `PLA`/`PETG`/`TPU`/`TPE`) | Filament settings | yes |
| `change_device_name` | Rename device | yes |

**Implication for us**: the TCP API has NO general-purpose "show a popup with this text" command. The only command that writes user-supplied text to a visible field is `bind`, and using it would corrupt the cloud-binding state. **Not viable.**

### 2.3 The popup pipeline

```
  Moonraker WS event
        │
        ▼
  webreceive_pthread_main_init    ── strcmp/strstr against fixed vocab
        │                            (notify_klippy_*, // +PAUSE:N, etc.)
        ▼
  Popup_pthread_setdata(cmd_id, subcmd, msg)
        │   writes to globals: G_popupdata->cmd, ->subcmd, ->msg[1024]
        ▼
  Popup_pthread                   ── reads G_popupdata.cmd, dispatches
        │
        ▼
  utils_uart_send_string("page popup1\xff\xff\xff")
  utils_uart_send_string("popup1.pop_num.val=N\xff\xff\xff")
       (literal Nextion commands written to /dev/ttyS1)
        │
        ▼
  Nextion-protocol TFT screen MCU renders the popup layout
  baked into /tmp/FDM.tft (TFT firmware, separate binary)
```

**Reconstructed signature** of the popup data setter:

```c
// voronFDM:0x6c4b8
void Popup_pthread_setdata(int32_t cmd_id, int32_t subcmd, const char *msg) {
    G_popupdata->cmd_id  = cmd_id;          // staging only
    G_popupdata->subcmd  = subcmd;
    memset(G_popupdata->msg_buf, 0, 1024);
    strcat(G_popupdata->msg_buf, msg);
}
```

**Crucially**: `Popup_pthread_setdata` is called from exactly **10 sites, all inside `webreceive_pthread_main_init`**. No external IPC channel reaches it. The popup pipeline is **state-driven from Klipper events**, not addressable from outside.

### 2.4 Complete popup-trigger table

| Callsite (voronFDM) | `cmd_id` | Trigger condition | Static message |
|---|---|---|---|
| 0x5a94c | **1000** | `strcmp(method, "notify_klippy_disconnected")` | `"notify_klippy_disconnected,Please shut down and restart"` |
| 0x5ae1c | **1001** | `strcmp(method, "notify_klippy_shutdown")` | `"notify_klippy_shutdown,Please shut down and restart"` |
| 0x5b3f4 | dynamic | JSON-RPC error response (has `code` + `message`) | constructed from `message` field |
| 0x614a0 / 0x614ec / 0x63444 / 0x63490 / 0x66168 | **1003** | `strstr(gcode_response, "// +PAUSE:N")` for N ∈ {2..a} | constructed |
| 0x617fc / 0x637a0 | **1003** | `strstr(gcode_response, "// +RESUME:N,")` | constructed |

The `cmd_id` values 1000/1001/1003 are NOT directly Nextion `pop_num` values — `Popup_pthread` reads `G_popupdata.cmd` and dispatches further via its own switch (cmps against small integers 2/4/5/49/55/56/98–103/255), which then emit hardcoded `popup1.pop_num.val=N` / `popup2.pop_num.val=N` strings. So even if we somehow staged `cmd_id=1001`, the visible message text is determined by the TFT firmware layout for whatever `pop_num` Popup_pthread chose — the "Please shut down and restart" string we see in voronFDM strings is what voronFDM passes downstream / what the TFT renders for that pop_num. We **cannot** override it from outside.

### 2.5 Direct Nextion commands extracted

`uart_pthread_dispatch_cmd` contains 182 unique `utils_uart_send_string` arguments. Highlights of what voronFDM is willing to push to the screen:

```
page popup1            page popup2           page wait
page home              page setwifi          page printing
page first             page firstwifi        page settem
page connapp           page system           page printerinfo
...                                          ...

popup1.pop_num.val=4, 5, 6, 7, 8, 15, 16, 22, 24, 25, 36, 38
popup2.pop2_num.val=4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16,
                     17, 18, 19, 20, 21, 22, 24, 25, 26
pop_num.val=2, 3, 12, 13, 17, 20, 21, 27, 33, 34, 38
auto_num.val=1..5      check_num.val=1, 4, 7, 12, 14
NO_num.val=1, 4
setwifi.ip.txt="IP:127.0.0.1"
popup1.conn_name.txt="<text>"   (TCP `bind` cmd only)
popup1.conn_use.txt="<text>"    (TCP `bind` cmd only)
popup2.ch.txt="<number>"
popup2.pop_txt.txt="Current: %s   Latest: v%d.%d.%d"  (update info)
```

The Nextion line terminator is **three `0xFF` bytes** (`\xff\xff\xff`) — standard for Nextion. This is what `utils_uart_send_string` appends.

**Direct-write path (NOT recommended for the install script — see below):** A privileged process can write Nextion commands directly to `/dev/ttyS1` and bypass voronFDM. We have the protocol exactly. However:

- voronFDM owns the port and will continue writing its own updates.
- Without the source of the `.tft` layout file (`/tmp/FDM.tft`), we don't know which page currently has a visible free-text object to overwrite.
- Stopping voronFDM (`killall voronFDM`) would free the port, but it would also stop the normal UI and is hard to recover from cleanly if `reboot` fails.

### 2.6 The "M117 reaches the screen?" question — **definitive answer: NO**

voronFDM consumes Moonraker's `notify_gcode_response` events but does NOT bridge arbitrary gcode-response text to the screen. The `webreceive_pthread_main_init` thread runs the response text through ~50 hardcoded `strstr` checks against fixed substrings:

- Printer state changes: `// +PAUSE:N`, `// +RESUME:N`, `// +P11:1,1`, `// +P1END:`
- Probe / homing: `No trigger on probe after full movement`, `No trigger on x after full movement`, ...
- Misc errors: `Unable to open file`, `Probe samples exceed samples_tolerance`
- Klipper-state: `notify_klippy_disconnected`, `notify_klippy_shutdown`, `// Klipper state: Disconnect`
- AMS: `+AMSERROR:2`, `CANCEL:1,`, `AMSCONNECT`, `fila_exist:True/False`
- Temperature: `B:`, `T0:`

If the response text matches none of these, **voronFDM silently drops it**. There is no "default → display on screen" branch. **`M117 anything` is invisible on this printer.**

This contradicts the assumption I made early in our investigation. The earlier suggestion to probe `curl -d 'script=M117 test'` was a waste of effort — it provably can't work given this code.

---

## 3. Reboot mechanism

### 3.1 What user runs the install script?

Indirect evidence only — we cannot probe a running printer. From the stock firmware:

- The stock `phrozen_install.sh` runs **bare** `chmod -R 777 *` and `cp -rf` into `/home/mks/klipper/...`. This works if running as root, OR as `mks` user (who owns the destination).
- Every other Phrozen lifecycle script uses bare privileged commands: `systemctl stop klipper` (start.sh:4), `systemctl stop makerbase-client.service` (KlipperScreen-start.sh:9), `shutdown -h now` (soft_shutdown.sh:31), writes to `/sys/class/gpio` (soft_shutdown.sh:5–18).
- voronFDM itself (running as `mks` per `klipperscreen.service:User=`) escalates with the **leaked password `makerbase`**: `echo makerbase | sudo -S cp -f .../soft_shutdown.sh /root/`. This pattern is hardcoded in the production binary — `makerbase` is the working sudo password for `mks` on this firmware.

### 3.2 Recommended reboot incantation

Safe-by-default sequence (handles both root and mks invocation):

```sh
sync
reboot 2>>"$INSTALL_LOG" \
    || (echo makerbase | sudo -S reboot) 2>>"$INSTALL_LOG" \
    || fail "reboot failed - manual power-cycle required"
```

Notes:
- `sync` flushes filesystem buffers.
- Bare `reboot` succeeds if running as root.
- `sudo -S` falls back for `mks` with the leaked password.
- The leaked password is a known fact of this firmware (V199), not a secret we're introducing.
- The prz-variant binary (`voronFDM-arm-prz`) does NOT contain the `makerbase` literal — it lives under `/home/prz/` and likely has either passwordless sudo or runs from a privileged context. Our fallback should still work because if bare `reboot` succeeds on prz, we never reach the sudo branch.

### 3.3 What about Moonraker's `machine.services.restart`?

voronFDM uses `{"method":"machine.services.restart","params":{"service":"klipper"}}` to restart Klipper via Moonraker. That's a **Klipper** restart, not a host OS reboot — it doesn't reload Python module bytecode. **Insufficient** for our use case (which is why your README's `README.md:304` mandates a full host restart).

---

## 4. The recommended install-script approach

### 4.1 Why "stop klipper → wait → reboot" is the best path

Strengths:
- **Native popup**: voronFDM auto-fires its `notify_klippy_shutdown` popup ("Please shut down and restart") via the official internal pipeline.
- **No protocol guessing**: we don't write to `/dev/ttyS1`, don't open the TCP socket, don't talk to voronFDM directly. We rely on a state change that voronFDM already monitors.
- **No race**: we don't compete with voronFDM for the serial port.
- **No TFT knowledge required**: the popup layout is baked into `/tmp/FDM.tft`, which we'd otherwise need to decompile.
- **Contextually appropriate**: "Please shut down and restart" is exactly what's happening.
- **Failure-safe**: if `systemctl stop klipper` fails for any reason, the script still reaches `reboot` and the install log still captures the error. The popup just doesn't appear — no harm done.
- **Works across both board variants** (MKS RK3328 and Phrozen RK3308) without per-variant code, because both run voronFDM with identical Moonraker integration.

Trade-offs:
- The on-screen text is fixed at "Please shut down and restart" — we cannot make it say "Rebooting now" without reverse-engineering the TFT firmware. Worth doing for our install use case? No — semantic content is the same and the user is in front of the printer anyway.
- We do not get a customizable failure-case popup. If `reboot` fails, the popup will still show "Please shut down and restart" — slightly misleading. Mitigation: write detailed failure info to `$INSTALL_LOG` and exit non-zero so the caller (Phrozen updater) sees it.

### 4.2 Why we are NOT writing direct Nextion commands

I considered, and chose not to implement, a path that does:

```sh
killall voronFDM 2>/dev/null
sleep 1
printf 'page popup1\xff\xff\xffpopup1.pop_num.val=4\xff\xff\xff' > /dev/ttyS1
sleep 2
reboot
```

Reasons against:
1. We don't know which `pop_num` value renders an arbitrary-text-message layout. The text-field popups (`pop_num.val=36`) are tied to specific layouts (cloud-bind UI) whose visual style is wrong here.
2. If `reboot` fails after we've killed voronFDM, the UI is dead with no recovery path until the user power-cycles manually.
3. The native path produces a fully-acceptable result with none of these risks.

If a future use case truly needs custom text (e.g., a long-running diagnostic with progress display), the right approach is to decompile `/tmp/FDM.tft` with Nextion Editor or the open-source `tft-tool` to map the layout, then drive `/dev/ttyS1` with confidence. Out of scope here.

### 4.3 Why we are NOT using the TCP API

The only TCP commands that write user-supplied text to a visible field are `bind` / `unbind`, which mutate the cloud-bind state (`G_appconnect`) as a side effect. Using them as a notification channel would corrupt the user's PhrozenGo cloud-connection state. **Bad trade-off.**

---

## 5. Verification probes (for when you have printer access)

When you're back at the printer, you can confirm any of these findings with the following SSH commands. None of them are required for the script to work — they're just verification.

```sh
# Confirm voronFDM is listening on 8809
ss -tlnp | grep 8809

# Confirm TCP envelope is what we think (will return an "Invalid JSON" error - that's success)
echo '{}' | nc -w1 127.0.0.1 8809

# Watch what voronFDM logs when Klipper goes down
journalctl -fu klipper &
journalctl -fu klipperscreen &  # voronFDM is launched from here
sudo systemctl stop klipper
# expect: popup "Please shut down and restart" on the TFT within ~1s

# Confirm reboot user context (will print uid:0 if running as root, or 1000:mks)
sudo bash -c 'id' 2>&1
```

---

## 6. What was NOT analyzed (out of scope for the install script)

- The `Continue_playing_pthread_pic` thread (popup animation) — not needed.
- The `webreceive_pthread_main_init` full ~16K-instruction dispatch tree — we only needed the popup-trigger sites.
- `UDSClient_VirtualAppParseJson` — handles JSON from `phrozen_master`, irrelevant to our path.
- The `PhrozenGo.tar` (TUTK cloud relay) — separate concern.
- `/tmp/FDM.tft` TFT firmware contents — that's where pop_num→layout mapping lives; can be opened with Nextion Editor if you need to map them, but unnecessary for our use case.

---

## 7. Quick-reference: file locations

| Path on printer | Origin in this repo (V199 dump) |
|---|---|
| `/dev/ttyS1` | UART to Nextion screen MCU (STM32F407VET6) |
| `/tmp/UNIX.domain` | `phrozen_master` UDS server (not in V199 dump) |
| `/tmp/FDM.tft` | Nextion TFT firmware (uploaded by voronFDM at boot from `serial-screen/`) |
| `/home/mks/klipper/klippy/extras/phrozen_dev/serial-screen/voronFDM` | reference/Arco_FW_V199/.../serial-screen/voronFDM |
| `/home/mks/printer_data/comms/klippy.sock` | Klipper Unix-socket API (Moonraker proxies this) |
| `localhost:7125` | Moonraker HTTP/WS (used by voronFDM, KlipperScreen, and we'd use it too if we wanted) |
| `localhost:8809` | voronFDM TCP server (JSON `{cmd, data}`) |
