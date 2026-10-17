# Warband on itch.io

Storefront: <https://ikamensh.itch.io/warband> (project `5172499`).

The page presents the playable game first: a short genre hook, genuine moving
gameplay, four faction identities, two campaigns, skirmish and multiplayer
features, then a direct invitation to play. The downloads are free, with no
donation interstitial. The development status is **In development / Early
Access**, not a finished release.

## Source of truth

This page and its gameplay media describe **v0.2.280**, source
`c9d74d8ac74dcb8f389cac8ed16e1cfa0223d5d2`. The live
[release catalogue](https://games.tachyon-ai.eu/releases.json), rather than old
release-pack prose, supplies the accepted packages and their checksums.
The hosted server's compatibility record matched this source when populated.

- `description.html`: the page body, including the hosted gameplay GIF.
- `install.html`: itch.io's download and installation instructions.
- `storefront.json`: title, discovery tags, theme, and accepted package identity.
- `cover.png` and `banner.png`: promotional title artwork generated with the
  built-in image generation tool, based on the game's existing shield icon.
- `art-prompts.json`: the actual generation prompts and reference assets.
- `screenshots/`: genuine native captures and their reproduction notes.

The page discloses AI-generated graphics, sound, writing and code. Promotional
artwork is distinguished from the actual gameplay captures. Only Windows x64
and Apple Silicon macOS have downloadable builds here; Linux and Intel Mac
support are not claimed.

## Presentation references

Reviewed on 2026-10-17:

| Page | Pattern used |
| --- | --- |
| [Mindustry](https://anuke.itch.io/mindustry) | Specific genre hook, concrete player actions, visible gameplay, direct downloads and support |
| [Songs of Syx](https://songsofsyx.itch.io/songs-of-syx) | Distinct gameplay pillars, clear development state, practical player information |
| [The Fertile Crescent](https://lincread.itch.io/the-fertile-crescent) | Classic RTS positioning, separate singleplayer and multiplayer value, precise platform and installation details |

Copy is original. The comparisons informed the structure, not the wording or art.
Itch.io's [creator guidance](https://itch.io/docs/creators/getting-started) calls
for a readable cover and three to five screenshots. The
[quality guidelines](https://itch.io/docs/creators/quality-guidelines) inform
accurate tags, AI disclosure and direct file hosting.

## Updating

1. Confirm the accepted release and server compatibility before replacing builds.
2. Download the accepted public packages and verify SHA-256 and file sizes.
3. Upload directly through itch.io, label the OS, architecture and version,
   and keep each file's purpose clear (installer, portable ZIP, or Mac app).
4. Update the local HTML and metadata alongside the saved page. Keep requirements
   and first-launch guidance aligned with the accepted packages.
5. Regenerate gameplay captures from that source using
   `tools/capture_storefront.py`; inspect them before replacing the originals.
6. Inspect desktop and narrow layouts, all image loads, and the public download
   flow. Verify a downloaded file against the accepted checksum.

Credentials belong in the personal secrets store, never in this directory.
Keep only the latest useful page verification under
`~/saga/evidence/warband/itch-storefront/`, with source and reproduction notes.
