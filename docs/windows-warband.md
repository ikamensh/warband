# Warband for Windows

Download the [0.2.0-preview.2 Windows installer](https://github.com/ikamensh/warband/releases/download/v0.2.0-preview.2/Warband-0.2.0-preview.2-windows-x64-setup.exe)
from the [Warband page](https://games.tachyon-ai.eu/warband/), which also has
the installation steps and service status.

Run the setup EXE and launch
**Warband** from the Start menu. The installer includes Python and all runtime
dependencies, installs for your account, and requires no administrator prompt.
The portable ZIP is an alternative: extract the entire `Warband` folder and
open `Warband.exe`, keeping its `_internal` folder beside it.

The [0.2.0-preview.2 release](https://github.com/ikamensh/warband/releases/tag/v0.2.0-preview.2)
includes an Apple Silicon Mac companion; what changed and its acceptance are
recorded in [warband-release.md](warband-release.md). See the
[Mac and Windows player guide](warband-play-together.md) for setup, controls,
first-launch prompts and reconnecting.

Preview.3 restores automatic worker gathering: idle peasants choose known
safe resources. Construction plans can borrow gatherers after cargo delivery;
movement, building, repair and patrol orders retain priority. Stop or Hold
keeps a worker parked until another order. Maps have broad meadows, groves,
ponds and rocky regions; new online rooms choose fresh maps. A stone rim and
corrected fog coverage contain the map artwork at its edge.
The new **Settlement** row lets you plan buildings, units and upgrades
without selecting a worker or building. **Plans** shows waiting reasons,
progress and cancellation; **Assembly point** sets where new soldiers gather.
Ground seam corrections have an independent
[native visual review](evidence/warband-map-workers-2026-09-08/visual-review.md),
including the final Settlement layout.

Preview.3 was built from `85becd0fda8493fffc14ad33baee32f4fccdee64`.
[Windows CI run 34216123836](https://github.com/ikamensh/saga2d/actions/runs/34216123836)
passed 357 scoped regression tests, extracted and installed executable checks,
public TLS multiplayer, native clipboard and settlement-planning input,
Start menu shortcut creation and uninstall. All nine native screenshots were
inspected. The [Windows evidence](evidence/warband-map-workers-2026-09-08/windows-package/README.md)
records exact hashes and test scope. Native CI used a test-only Mesa driver;
physical Windows GPU performance and audible sound quality remain unverified.
The [public download receipt](evidence/warband-map-workers-2026-09-08/published-release.json)
records the independently downloaded shipping files.

Historical acceptance remains available separately. **Preview.2** passed
[Windows CI run 34208548272](https://github.com/ikamensh/saga2d/actions/runs/34208548272),
including package, public multiplayer, native clipboard/menu and uninstall
checks. Its three published downloads passed an independent
[public download/hash check](evidence/warband-easy-online-2026-09-08/published-release.json).
**Preview.1** passed 285 scoped tests and package/native checks in
[CI run 34202934123](https://github.com/ikamensh/saga2d/actions/runs/34202934123);
its [retained evidence](evidence/warband-internet-2026-09-08/windows-package/README.md)
records the scope. These results do not establish preview.3 acceptance.

Choose **Multiplayer → Create room → Copy room code** and send it to your partner.
They choose **Multiplayer → Paste code → Join room**. Internet matches use the default
hosted server; no router configuration or incoming firewall rule is needed.
Use **Rejoin last room** after a disconnect while the room remains available.
The match continues while its **Match menu** is open; use **Leave match**
to return to the title.

Windows 10/11 with x64 application support and a pyglet-compatible OpenGL
driver are the intended target. Preview installers are unsigned; Windows
may display an unknown-publisher warning. Save files, settings and generated
sound assets live under `%USERPROFILE%\.warband`. Uninstall through Windows
Installed apps; your saved games remain available for a later reinstall.

## Build and verification

The [native package workflow](../.github/workflows/native-packages.yml) builds
Windows x64 on `windows-2025` and Apple Silicon macOS on `macos-15`. Branch
pushes, pull requests and manual runs produce verified CI artifacts. Both
platforms use one recorded source/dependency identity and a preview version
derived from the run ID. Retry publication from the accepted build run; do not
rebuild an existing release identity.

The separate [publisher](../.github/workflows/publish.yml) consumes successful
native runs on `main`. Its write job requires `WARBAND_PUBLISH_ENABLED=true`;
enabling it and Saga Online promotion is tracked in the
[CI publication plan](ci-publication.md). The old tag-triggered Windows-only
workflow has been removed. Existing versioned releases are never overwritten.

The local Windows build commands are:

```powershell
uv run --extra package python tools/package.py build --version 0.2.0-preview.2 --installer --require-clean
uv run --extra package python tools/package.py verify dist/warband --native --public-server wss://games.tachyon-ai.eu/play
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

The native producer verifies sockets against its pinned local server. Public
server compatibility and packaged create/join checks are separate promotion
and rollout requirements. The local command above also repeats the installed
executable's checks over TLS against `wss://games.tachyon-ai.eu/play`, records
the result in `verification.json` and creates one short-lived room. Omit
`--public-server` for local-only verification.

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
