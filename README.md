# steam-ungarbage

This is a utility to clean steam created URL links and uninstall info on Windows, Linux and macOS.

This tool **does not** prevent Steam from creating those links.

Currently tested on Windows and macOS.

## Why I am making this

Steam creates shortcut URLs (and uninstall info on Windows) that launches Steam upon clicking.

For me it offers no convenience and may cause more misclicks in daily usage. (steam itself is a launcher though)

However, there does not seem to have an option to disable this.

## What are being cleaned

- **Windows**: Steam desktop & Start Menu `.url` shortcuts, Epic desktop `.url` shortcuts (`com.epicgames.launcher://`, Epic only writes to the desktop), and Steam `Steam App <appid>` uninstall entries in the registry
- **Linux**: `.desktop` files and icons created in the home data folders, and Desktop icons
- **macOS**: Pseudo `.app` files created under `~/Applications`

## Running

Run:

```bash
uvx steam-ungarbage # (or uv tool run steam-ungarbage)

# For newer windows run:
sudo uvx steam-ungarbage

# Run locally
uv run steam-ungarbage
```
