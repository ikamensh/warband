# Warband for Windows

Download `Warband-VERSION-windows-x64-setup.exe` from the repository's
[releases](https://github.com/ikamensh/saga2d/releases). Run it and launch
**Warband** from the Start menu. The installer includes Python and all runtime
dependencies, installs for your account, and requires no administrator prompt.
The portable ZIP is an alternative: extract the entire `Warband` folder and
open `Warband.exe`, keeping its `_internal` folder beside it.

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
uv run --locked --python 3.13.2 python tools/verify_warband_package.py dist/warband --native
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

Native title, multiplayer input and match rendering are attempted separately.
Known missing graphics-context errors produce an explicit unsupported-runner
receipt. Other rendering, import or asset errors fail verification. The PNGs
and all diagnostic JSON/logs are retained in the CI artifact for 30 days.
These checks cover the recorded runner; real Windows GPU/audio playtesting
and public-server gameplay verification are separate evidence.

Inno Setup's [non-administrator setting](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm),
[installer parameters](https://jrsoftware.org/ishelp/topic_setupcmdline.htm)
and [architecture rules](https://jrsoftware.org/ishelp/topic_archidentifiers.htm)
define the installer behavior. The compiler is supplied by the
[Windows runner image](https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-Readme.md).
