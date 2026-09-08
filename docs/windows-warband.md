# Warband for Windows

Download the [0.1.0-preview.1 Windows installer](https://github.com/ikamensh/saga2d/releases/download/warband-v0.1.0-preview.1/Warband-0.1.0-preview.1-windows-x64-setup.exe).
Run it and launch
**Warband** from the Start menu. The installer includes Python and all runtime
dependencies, installs for your account, and requires no administrator prompt.
The portable ZIP is an alternative: extract the entire `Warband` folder and
open `Warband.exe`, keeping its `_internal` folder beside it.

The [preview release](https://github.com/ikamensh/saga2d/releases/tag/warband-v0.1.0-preview.1)
also includes an Apple Silicon Mac app for your partner, exact checksums and
verification receipts. The installer passed [Windows CI run 34202934123](https://github.com/ikamensh/saga2d/actions/runs/34202934123),
including 285 scoped tests, public multiplayer, native rendering and uninstall.
The [retained evidence](evidence/warband-internet-2026-09-08/windows-package/README.md)
records what was checked. All three published application downloads were
downloaded without authentication and matched the inspected artifact hashes.

Choose **Multiplayer → Create room** and share the room code with your partner.
They choose **Multiplayer → Join room**. Internet matches use the default
hosted server; no router configuration or incoming firewall rule is needed.
Use **Rejoin last room** after a disconnect while the room remains available.

Windows 10/11 with x64 application support and a pyglet-compatible OpenGL
driver are the intended target. The current installer is unsigned; Windows
may display an unknown-publisher warning. Save files, settings and generated
sound assets live under `%USERPROFILE%\.warband`. Uninstall through Windows
Installed apps; your saved games remain available for a later reinstall.

## Build and verification

The [Windows workflow](../.github/workflows/warband-windows.yml) runs on
`windows-latest`. Dispatch it with an explicit version to create a downloadable
CI artifact, or push an immutable `warband-vVERSION` tag to publish a release
after the checks pass. A manual publication also requires the matching tag
to resolve to the dispatched commit. Existing releases are never overwritten.

The local Windows build commands are:

```powershell
uv run --locked --isolated --python 3.13.2 --with-requirements packaging/requirements.txt python tools/build_warband.py --version 0.1.0-preview.1 --installer --require-clean
uv run --locked --python 3.13.2 python tools/verify_warband_package.py dist/warband --native --public-server wss://games.tachyon-ai.eu/play
```

The builder snapshots source files, records their hashes and exact Git commit,
uses pinned CPython/PyInstaller tools, bundles dependency licenses, and emits
the portable ZIP, per-user Inno Setup installer, `build-manifest.json` and
`SHA256SUMS`. The manifest records build provenance; runtime acceptance is
recorded separately in `verification.json`.

CI first runs Warband and shared transport regression tests. It then extracts
the ZIP and runs its actual executable outside the checkout with an isolated
profile and no Python on PATH. Two clients create/join a real local WebSocket
room, reject an opponent's command, move a server-owned unit and reconnect a
private seat. CI also installs the EXE, checks its Start menu shortcut, repeats
the executable check, uninstalls, and checks that the program and shortcut are
removed. These checks use the production room handler and simulation.

Before uninstalling, CI repeats the installed executable's multiplayer checks
over TLS against `wss://games.tachyon-ai.eu/play`. This required public-server
check records its endpoint and results in `verification.json` and creates one
short-lived room on the hosted service. Omit `--public-server` for a local-only
verification run.

Native title, multiplayer input and match rendering must also pass. Because
the Windows runner has only Microsoft's legacy OpenGL driver, CI supplies
[Mesa llvmpipe](https://docs.mesa3d.org/drivers/llvmpipe.html) for the native
test using the SHA-256-pinned
[26.2.0 Windows build](https://github.com/pal1000/mesa-dist-win/releases/tag/26.2.0).
Its two WGL DLLs are placed beside the installed EXE only for this check and
removed afterward. They are absent from the installer and portable ZIP.
The receipt records the exact EXE hash, actual GL renderer/version and both
test DLL hashes; `mesa-test-context.json` records download provenance.
To reproduce this setup, add `--mesa-dir PATH` pointing to those x64 DLLs.
Any native rendering failure fails CI. The PNGs and all diagnostic JSON/logs
are retained in the CI artifact for 30 days.
These checks cover the recorded runner; real Windows GPU/audio playtesting
and a match against the remote AI are separate evidence.

Inno Setup's [non-administrator setting](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm),
[installer parameters](https://jrsoftware.org/ishelp/topic_setupcmdline.htm)
and [architecture rules](https://jrsoftware.org/ishelp/topic_archidentifiers.htm)
define the installer behavior. The compiler is supplied by the
[Windows runner image](https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-Readme.md).
