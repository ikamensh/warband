# Warband — release pack (0.1.0-preview.4)

The [Warband page](https://games.tachyon-ai.eu/warband/) offers the current
downloads with installation steps; the same files are on the published
[preview.4 release](https://github.com/ikamensh/saga2d/releases/tag/warband-v0.1.0-preview.4):
the [Windows installer](https://github.com/ikamensh/saga2d/releases/download/warband-v0.1.0-preview.4/Warband-0.1.0-preview.4-windows-x64-setup.exe)
and [Apple Silicon Mac app](https://github.com/ikamensh/saga2d/releases/download/warband-v0.1.0-preview.4/Warband-0.1.0-preview.4-darwin-arm64-app.zip),
built from `6f58eca12b7f4a969a063227267637256413c8ae`.
See the [Mac and Windows player guide](warband-play-together.md) for practical
installation and play instructions.

## Local install on this Mac

`uv run --extra package python tools/package.py install` builds the app from the clean
working tree under the pinned packaging environment (version
`<project version>-local.<commit>`), self-tests the fresh bundle, backs the
installed `/Applications/Warband.app` up under `dist/local-app-backups/`,
copies the new bundle in with `ditto` and self-tests it again; a receipt with
the commit and executable hash lands in `dist/warband-local/`.  `--skip-build
--output DIR` installs a bundle already built there; `--allow-dirty` builds an
uncommitted tree.  The same script installs Tribes.

## Changes in preview.4

- The waiting screen offers **Copy invite link** beside **Copy room code**.
  The link opens `https://games.tachyon-ai.eu/join/warband-v1/<code>`, which
  shows the code, the joining steps and the download for a friend without
  the game. It never contains the private seat.
- The waiting screen states how long the seats are kept without both players.
- Multiplayer checks the published release catalog and shows **Update
  available** with an **Open download page** button when a newer build
  exists. A client the server no longer accepts sees **Update required** with
  the same button instead of a bare error.
- Gameplay, art and rules are unchanged from preview.3.

## Acceptance: preview.4

Source: `6f58eca12b7f4a969a063227267637256413c8ae`.

[Windows CI run 34229830340](https://github.com/ikamensh/saga2d/actions/runs/34229830340)
built the installer and portable ZIP, passed the scoped regression tests and the
extracted, installed, public TLS and native (test-only Mesa) package checks,
Start menu shortcut creation and uninstall, then published the release. The Mac
portable executable passed loopback socket and native checks on Apple M4,
including the new invite-link button; the installed `/Applications/Warband.app`
passed the online diagnostics against `wss://games.tachyon-ai.eu/play`. All
three public downloads were fetched without authentication and matched the
manifests. Evidence: [warband-distribution-2026-09-08](evidence/warband-distribution-2026-09-08/).

| File | SHA-256 |
|---|---|
| `Warband-0.1.0-preview.4-windows-x64-setup.exe` | `d03cc766d54b264de41b771a975881b82a4a1d061157fb483647d262a6fd8e53` |
| `Warband-0.1.0-preview.4-windows-x64-portable.zip` | `64b878f94e52cf0a72289a53053a3716e0bc1010cfbd3abd54ea411e5bf88f9e` |
| `Warband-0.1.0-preview.4-darwin-arm64-app.zip` | `03ab70b254f76897cd252a54612fab1a8599ec13786e5e16b888828e39e3b81a` |

The remaining preview limits are unchanged: unsigned Windows installer,
ad-hoc signed Mac app, and no complete human-versus-human playtest.

## Historical: preview.3

[Preview.3](https://github.com/ikamensh/saga2d/releases/tag/warband-v0.1.0-preview.3)
was built from `85becd0fda8493fffc14ad33baee32f4fccdee64`.

### Changes in preview.3

- Restored automatic worker gathering from the earlier app: idle peasants
  balance needed gold and lumber and use known safe resources and routes.
  Construction plans can borrow gatherers after cargo delivery; movement,
  building, repair and patrol orders retain priority. Stop or Hold parks a
  worker until another order enables automatic work again.
- Meadows, woodland groves, ponds and rocky regions give maps distinct areas
  while preserving accessible bases and connecting routes.
- Every newly created online room receives a fresh map seed. Command-line
  hosting also chooses a fresh seed when none is supplied; an explicit
  `--seed` remains reproducible.
- A stone rim and corrected fog coverage prevent map artwork from spilling
  beyond the playable edge. Extruded atlas padding and consistent ground
  overlap remove straight seams between terrain chunks.
- The global Settlement row offers Build, Train, Upgrade, Plans and Assembly
  point without a selection. Requests wait for resources, prerequisites,
  workers, production capacity and supply; the live Plans panel shows
  progress and cancellation.
- Transparent panels retain the map's camera position and zoom, including
  when the second player opens Plans or the Match menu.

The [independent native visual review](evidence/warband-map-workers-2026-09-08/visual-review.md)
records the final map appearance across all three themes and Settlement UI
captures. Package acceptance is recorded below.

Preview.2's room-code copy/paste buttons, keyboard paste and live multiplayer
menus remain included. Historical validation below is scoped to those earlier
releases and does not establish preview.3 acceptance.

## Store description (draft)

**Warband** is a snappy real-time strategy skirmish in the classic mould:
gather gold and lumber, raise a base, train an army and raze the rival's.
Matches take ten to twenty minutes against an AI that plays a recognisable
strategy, on procedural maps that change your opening.

- Seven units with real roles: peasants, footmen, archers, scouts, knights,
  catapults that batter walls with splash damage, and clerics who heal.
- Nine buildings and a short tech chain: farms, barracks, lumber mill,
  blacksmith, stables, workshop, church and guard towers; nine upgrades;
  peasants repair what the enemy leaves standing.
- Three AI difficulties that build, expand, upgrade, raid and attack in
  growing waves.
- Procedural maps in three sizes and three lands — summer, winter and
  wasteland — with regional meadows, groves, ponds and stone. Offline games
  support two to four factions; internet rooms have two player seats.
- Idle peasants find known safe work automatically; construction plans can
  borrow gatherers after cargo delivery. Other tasks keep priority, and Stop
  or Hold keeps a worker parked.
- Mouse controls and keyboard shortcuts support drag or click to select,
  right-click to order, attack-move, patrol, hold, rally points,
  control groups, camera bookmarks, a minimap that pans and orders.
- A tutorial strip and saves with an autosave every two minutes for offline
  matches; a codex, persistent settings, fullscreen and online seat reconnects.
- Original procedural art and music: every sprite, sound and track is
  generated by the game.

## Controls

See the in-game help (F1) and codex (F2). Summary:

| Action | Keys |
|---|---|
| Select | click, drag a box, double-click or Ctrl-click for a type, Ctrl+A for the army, 1–9 groups (Ctrl+1–9 to set), Tab / . next idle peasant / soldier |
| Order | right-click (move, harvest, attack, repair, resume building, rally), A attack-move, P patrol, S stop, H hold, M move, R repair |
| Plan without a selection | Settlement → Build / Train / Upgrade (Ctrl+B / Ctrl+T / Ctrl+U, Shift+letter orders five in Train); Ctrl+P Plans shows waiting work, progress and cancellation; Ctrl+G assembly point |
| Build with a selected worker | B then F farm, B barracks, H town hall, T tower, M lumber mill, K blacksmith, S stables, W workshop, C church |
| Train / research directly | the letters on the command card when a building is selected |
| Gather new soldiers | Assembly (Ctrl+G), then click the map; a building-specific rally point takes priority |
| Park an automatic worker | S or H; another order enables automatic work again |
| Mac trackpad | two-finger click or Ctrl+click is the right-click; Cmd-click selects every unit of a type |
| Camera | arrows, screen edges, middle-drag, wheel or + / − zoom, F6–F8 bookmarks (Ctrl to set), Space jumps to the last alert, Home or Backspace to the base |
| Menu | F10 opens the menu; Esc cancels, deselects, then opens it. Online: Match menu → Leave match returns to the title. |
| Offline only | F3 pause, F4 hide the tutorial strip, F5 quicksave, F9 quickload. Online matches continue while menus are open. |

## Known issues in this preview

- Units use discrete animation poses; workers have four additional chopping poses with coordinated axe and body motion.
- The layout uses a fixed logical canvas. Fullscreen helps readability; scaling the window does not rearrange its panels.
- Large maps with three or four players can run past twenty minutes without a decision.
- Preview.3 passed automated Windows package, native input and public multiplayer checks with a test-only Mesa driver. Physical Windows GPU performance and audible sound quality remain unverified. The installer is unsigned.
- Preview.3 passed macOS native input/rendering and public multiplayer checks on Apple M4. The Mac app uses ad-hoc signatures without Developer ID notarization. Independent playtesting and a complete human-versus-human match remain open.
- No standalone Linux package has been produced or verified. Running the server and headless AI on Linux does not establish desktop-package compatibility.
- No localisation; English only.

## Credits and provenance

- Design, code, art generators and music generators: created in this
  repository (see the git history). No third-party art or audio is used;
  every image and sound is generated at runtime by `warband/textures.py`
  and `warband/sound.py`.
- Font: Nunito by Vernon Adams, Cyreal and Jacques Le Bailly, SIL Open
  Font License 1.1 (`saga2d/assets/fonts/OFL.txt`).
- Engine: saga2d (this repository, MIT) on pyglet (BSD), Pillow (HPND),
  NumPy (BSD).

## Support and feedback

Issues and feedback: the repository's issue tracker. Saves and settings live
in `~/.warband` (`settings.json`, `saves/`, generated `sounds/` and
`music/`); deleting the folder resets the game.

### Acceptance: preview.3

Source: `85becd0fda8493fffc14ad33baee32f4fccdee64`.

[Windows CI run 34216123836](https://github.com/ikamensh/saga2d/actions/runs/34216123836)
passed 357 scoped regression tests and checks of the extracted portable and
installed executables. Public TLS multiplayer, native clipboard and planning
input, Start menu shortcut creation and uninstall passed. All nine native
frames were visually inspected. Test-only Mesa DLLs are absent from both
shipping packages. [Windows acceptance evidence](evidence/warband-map-workers-2026-09-08/windows-package/README.md).

The Mac portable executable passed loopback socket and native checks. The
final `/Applications/Warband.app` separately passed public TLS multiplayer
and native input/rendering on Apple M4. Checks included automatic builder
assignment, global unit/upgrade plans, assembly, cancellation and seat rejoin.
All nine portable and nine installed native frames were inspected. Extracting
the app archive preserved the installed executable hash and passed deep,
strict ad-hoc signature verification. The previous installed app is backed up;
settings and saves were preserved.
[Mac acceptance evidence](evidence/warband-map-workers-2026-09-08/mac-package/README.md).

All three public downloads were retrieved without authentication and matched
the tested artifacts, checksum file, manifests and GitHub release digests.
The [delivery receipt](evidence/warband-map-workers-2026-09-08/published-release.json)
records source, publication time, sizes and hashes.

| File | SHA-256 |
|---|---|
| `Warband-0.1.0-preview.3-windows-x64-setup.exe` | `10a1a78748f9b2954fa3a18119dee359d8254d4e36efb8226032e1fd1d190a26` |
| `Warband-0.1.0-preview.3-windows-x64-portable.zip` | `945fcccc5055781d43c6c725b4c0da94bcff1ca406e90fa17ef8bb172bae2de7` |
| `Warband-0.1.0-preview.3-darwin-arm64-app.zip` | `4b968c2d3f1aea2c06c0dae2e1916585dc32256340757ac5baf6528f1688c356` |

Creating the release tag triggered a redundant build at the same source.
Its build and verification passed; publication stopped because this immutable
release already existed. The shipping files above come from the accepted
manual run and Mac build, and were not replaced by that duplicate run.

## Historical acceptance: preview.2

[Preview.2](https://github.com/ikamensh/saga2d/releases/tag/warband-v0.1.0-preview.2)
was published on 2026-09-08 from
`02377270d59fcf2ee6e9b0eef897303c1a5c0903`.
[Windows CI run 34208548272](https://github.com/ikamensh/saga2d/actions/runs/34208548272)
passed its regression, package, public TLS, native clipboard/menu and uninstall
checks. The corresponding Mac app passed public TLS and native clipboard/menu
checks on Apple M4. These checks exercised the actual packaged executables;
they were not a complete match between two human players.

All three published downloads were retrieved without authentication and
matched their local binaries, checksum files, manifests and public release
digests. The [delivery receipt](evidence/warband-easy-online-2026-09-08/published-release.json)
records exact file names, sizes and hashes; the
[package evidence](evidence/warband-easy-online-2026-09-08/) records runtime scope.

## Historical acceptance: preview.1

Windows release **0.1.0-preview.1** was built from immutable commit
`fd6e0c911fa68aa0355d4b56dd8e4f0885c739d8` on 2026-09-08.
[CI run 34202934123](https://github.com/ikamensh/saga2d/actions/runs/34202934123)
passed regression tests, pinned packaging, extracted and installed executable
checks over real local sockets, installed-executable checks against the public
TLS server, native title/menu/match rendering, Start menu shortcut creation
and uninstall. The runtime checks include accepted movement, rejected foreign
orders and private-seat reconnection.

The native Windows check used Mesa 26.2.0 llvmpipe on the Windows Server 2025
runner. Those test DLLs are absent from the shipping installer and ZIP.
Generation/loading of the 87-sound catalog was checked with audio muted;
this is not a listening test. See [Windows verification details](windows-warband.md).

Exact published preview.1 artifacts:

| File | SHA-256 |
|---|---|
| `Warband-0.1.0-preview.1-windows-x64-setup.exe` | `f2fcabad5bb14dde52630246005f900c37c0f80d2d46d12d433966c1e603500b` |
| `Warband-0.1.0-preview.1-windows-x64-portable.zip` | `65168d56f015a7caeaa5774d2ab6e50d62f34118375cc1f9645a0d7808675368` |
| `Warband-0.1.0-preview.1-darwin-arm64-app.zip` | `5d918cf308436c0f6e81f7b6893e8cf50b529842740e2075f08b95742867dedf` |

The macOS arm64 companion was built from the same immutable `fd6e0c9` source.
Its portable executable passed isolated launch, fonts, native input/rendering
and local network checks. The final `.app` separately passed public TLS and
native rendering on Apple M4; archive extraction preserved the executable
hash and passed deep, strict ad-hoc signature verification. See the
[final Mac package evidence](evidence/warband-internet-2026-09-08/mac-release/README.md).
This delivered build supersedes the earlier Mac candidate at `90f3067`.

`build-manifest.json` records build provenance; `verification.json` records
runtime acceptance. Neither replaces testing on players' hardware or an
independent multiplayer playtest.
