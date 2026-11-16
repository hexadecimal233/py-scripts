# adb-export-tabs

Export the tabs currently open in a Chromium-based Android browser as a Markdown list or JSON, over adb. No root required.

While the browser process is alive it exposes a DevTools abstract socket; `adb forward` is pointed at it and `/json/list` is read over the DevTools HTTP endpoint.

## Requirements

- `adb`, taken from `$ADBUTILS_ADB_PATH`, `PATH`, or the binary bundled with `adbutils`
- a USB-connected, authorized device with the browser running

## Usage

```bash
adb-export-tabs                      # Markdown list with a header
adb-export-tabs --json               # JSON array
adb-export-tabs -o tabs.md           # write to a file
adb-export-tabs --list-devices       # just list devices and exit
adb-export-tabs --serial R58M1234AB  # pick one of several devices
adb-export-tabs --socket chrome_devtools_remote
```

Run it from this repo without installing:

```bash
uv run adb-export-tabs --help
```

## Notes

- The DevTools socket only exists while the browser is running; if `adb forward` succeeds but the HTTP request fails, the browser has exited or is a version that does not expose the socket.
- Only targets of type `page` with a non-`devtools://` URL are exported.
