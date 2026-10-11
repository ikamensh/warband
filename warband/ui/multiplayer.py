"""LAN and online match scenes; authority lives in warband.online.authority."""
import math
import time
from urllib.parse import urlsplit

from saga2d import Anchor, Button, Column, CommandError, Label, MatchLobby, MatchMenu, Row, Settings
from saga2d.network import MatchClient, MatchHost
from saga2d.settings import SettingsError
from warband.records.profile import Profile, SaveError
from warband.sim import mapgen
from warband.sim.model import Event, RuleError, World
from warband.sim.races import RACES
from warband.sim.rules import SIM_DT, Layout, MapTheme, Race
from warband.ui.scene import GameScene, HelpScene, SettingsScene, _Overlay, _clock
from warband.ui.style import ACTION_BUTTON, GHOST_BUTTON, MENU_BUTTON, OVERLAY_STYLE, PANEL_STYLE, PICKED_BUTTON
from warband.ui.view import check_memory

GAME_ID = "warband-v2"
ROOM_SEATS = (2, 3, 4)
IDENTITY_FILE = "online-identity.json"


IDENTITY_DEFAULTS = {"tokens": {}, "profiles": {}}


def _default_endpoint() -> str:
    """This build's room server URL."""
    from saga2d.online import server_endpoint
    return server_endpoint()


def _identity_store(game) -> Settings:
    """This computer's private online record: per-endpoint server tokens and the cached own profile.

    A damaged record raises :class:`SettingsError` with the decode context; the damaged
    bytes stay unchanged on disk — never reset, replaced, recovered or started fresh here.
    Callers surface the error once so the player hears about it.  A missing record
    legitimately starts on defaults.  The private seat never leaves this computer except
    through the server's own resume mechanism."""
    store = Settings(game.data_dir / IDENTITY_FILE, IDENTITY_DEFAULTS)
    if store.error:
        raise SettingsError(f"Online identity record damaged ({store.error}); "
                            "the file is kept unchanged.")
    return store


def identity_notice(game) -> str:
    """Non-empty when the private identity record on disk is damaged: the file is kept
    unchanged; restore that record before connecting."""
    probe = Settings(game.data_dir / IDENTITY_FILE, IDENTITY_DEFAULTS)
    if probe.error:
        return ("Online identity record damaged — the file is kept unchanged. "
                "Restore that record before connecting.")
    return ""


def display_name(game) -> str:
    """This computer's player name: the local profile's.

    A damaged profile raises :class:`SaveError`; scenes surface it once instead of silently
    substituting Commander.  A missing profile never reaches here: ``Profile.load`` owns
    that default."""
    return Profile.load(game.data_dir).name


def online_identity(game, endpoint: str | None = None) -> dict:
    """Public kwargs identifying this computer's player to the room server.

    Returns ``{"player_token", "player_name"}``: the server-issued per-endpoint token —
    ``""`` until a room issues one, since the server owns registration and rejects
    tokens it never minted — and the local profile's display name."""
    store = _identity_store(game)
    key = endpoint or _default_endpoint()
    tokens = dict(store["tokens"])
    if key not in tokens:
        token = ""
    elif not isinstance(tokens[key], str):
        raise SettingsError("Online identity record has a malformed token for this server; "
                            "the file is kept unchanged.")
    else:
        token = tokens[key]
    return {"player_token": token, "player_name": display_name(game)}


def stored_online_profile(game, endpoint: str | None = None) -> dict | None:
    """The cached own server profile for *endpoint*, or ``None`` when no match has reported one.

    Never the offline skirmish rating: until the server names this player, the card says so."""
    store = _identity_store(game)
    key = endpoint or _default_endpoint()
    profiles = dict(store["profiles"])
    if key not in profiles:
        return None
    profile = profiles[key]
    if not isinstance(profile, dict):
        raise SettingsError("Online identity record has a malformed profile for this server; "
                            "the file is kept unchanged.")
    return profile


def _is_online(session) -> bool:
    """Whether *session* is an online room rather than LAN: LAN sessions predate the flag."""
    return getattr(session, "online", False)


def session_profile(session) -> dict | None:
    """The live own server profile — ``{player_id, name, rating, games, wins, losses}`` — or ``None``."""
    if not _is_online(session):
        return None
    profile = session.rating
    return profile if isinstance(profile, dict) else None


def session_result(session) -> dict | None:
    """The live authoritative rated result — ``{match_id, winner, ratings:[{player_id, name,
    before, after, delta, games, wins, losses}]}`` — or ``None`` while it has none."""
    if not _is_online(session):
        return None
    result = session.result
    return result if isinstance(result, dict) else None


def session_rated(session) -> bool:
    """Whether this session's room plays rated: LAN rooms never do."""
    return _is_online(session) and session.rated is True


def format_rating(value, *, signed: bool = False) -> str:
    """Server Elo as players read it: whole numbers plain, fractions to one decimal.

    ``1500`` and ``1500.0`` read ``1500``; ``+16.0`` reads ``+16``; ``+10.666`` reads
    ``+10.7``.  Engine deltas are floats, including fractional free-for-all shares, so
    every rating shown passes through here rather than an integer format."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"a rating is a number, not {type(value).__name__}")
    if isinstance(value, float) and value != int(value):
        text = f"{value:.1f}"
    else:
        text = str(int(value))
    if signed and not text.startswith(("+", "-")):
        text = "+" + text
    return text


def rated_grace_clause(session) -> str:
    """The rated departure grace as the server configured it — never a hard-coded number.

    ``rated_grace`` is ``None`` before the welcome or on legacy casual rooms; then the clause
    names the forfeit without seconds.  Both-offline rooms pause; the first reconnect gives
    the other active seats the full window while a connected opponent remains."""
    grace = session.rated_grace
    if isinstance(grace, (int, float)) and grace > 0:
        return (f"A rated seat alone for over {grace:g} s forfeits "
                "while an opponent stays connected.")
    return "A rated room: a seat left alone forfeits while an opponent stays connected."


def refresh_online_identity(game, session) -> None:
    """Save the latest own server token and profile into the endpoint identity record.

    The lobby and ``NetworkGameScene`` polling call this on change only, so the setup rating
    card stays current when returning from a match without writing the file every poll.
    Only the token and the profile are cached: the id already lives in the profile and
    the result only ever lives on the session.  The offline profile is never substituted."""
    endpoint = session.endpoint or ""
    if not endpoint:
        return
    token = session.player_token
    profile = session_profile(session)
    store = _identity_store(game)
    changed = False
    if isinstance(token, str) and token and dict(store["tokens"]).get(endpoint) != token:
        tokens = dict(store["tokens"])
        tokens[endpoint] = token
        store["tokens"] = tokens
        changed = True
    if isinstance(profile, dict) and store["profiles"].get(endpoint) != profile:
        profiles = dict(store["profiles"])
        profiles[endpoint] = profile
        store["profiles"] = profiles
        changed = True
    if changed:
        store.save()


def _dims_le(pair: tuple[int, int], cap: tuple[int, int]) -> bool:
    return pair[0] <= cap[0] and pair[1] <= cap[1]


class MatchSetupMenu(MatchMenu):
    """Warband's own room setup: a create card and a join card in gold and iron.

    Room settings live here, never on the title's skirmish: whatever offline size or
    seat count is chosen, opening multiplayer always works, on valid room defaults.
    Create and join send identity, ``rated`` and the shared faction choice; rejoin
    sends the stored identity only."""

    def __init__(self, settings=None) -> None:
        self.settings = settings
        self.rated = True
        self.seats = 2
        self.size = "Medium"
        self.theme = MapTheme.SUMMER
        self.faction = Race.HUMAN
        self.layout: Layout | None = None
        self.magic = False
        self._profile_name = "Commander"
        self._profile_error = ""
        self._identity_notice = ""
        self._stored_profile: dict | None = None
        super().__init__("Warband multiplayer", GAME_ID, self.create_match, self.create_scene,
                         create_options=self.create_options)
        self._settle()

    def on_enter(self):
        self._load_identity_display()
        super().on_enter()

    def on_reveal(self):
        self._load_identity_display()
        super().on_reveal()

    def _load_identity_display(self) -> None:
        """Read the display name, notices and cached profile once per showing — never per draw."""
        try:
            self._profile_name = Profile.load(self.game.data_dir).name
            self._profile_error = ""
        except SaveError as exc:
            self._profile_name, self._profile_error = "Commander", str(exc)
        try:
            self._identity_notice = identity_notice(self.game)
            self._stored_profile = stored_online_profile(self.game)
        except (SettingsError, OSError) as exc:
            self._identity_notice = f"Online identity unreadable: {exc}"
            self._stored_profile = None

    # -- The room's own options ----------------------------------------------------

    def online_sizes(self, seats: int | None = None) -> tuple[str, ...]:
        """The sizes seating *seats* that a room may ask for: fair ones up through Large."""
        from warband.online.authority import ONLINE_SIZE
        seats = self.seats if seats is None else seats
        sizes = tuple(name for name in mapgen.sizes_for(seats)
                      if _dims_le(mapgen.dimensions(name, seats), ONLINE_SIZE))
        if not sizes:
            raise ValueError(f"No room size seats {seats}: 2–4 seats always offer a real size.")
        return sizes

    def room_dimensions(self, seats: int | None = None) -> tuple[int, int]:
        """The map the room plays: the chosen size, moved to one seating them if it does not."""
        seats = self.seats if seats is None else seats
        sizes = self.online_sizes(seats)
        return mapgen.dimensions(self.size if self.size in sizes else sizes[0], seats)

    def room_layouts(self, seats: int | None = None) -> tuple[Layout, ...]:
        seats = self.seats if seats is None else seats
        width, height = self.room_dimensions(seats)
        return mapgen.layouts_for(width, height, seats)

    def _settle(self) -> None:
        """Keep size and layout a combination the room can hold: what no longer fits falls back."""
        sizes = self.online_sizes()
        if self.size not in sizes:
            self.size = sizes[0]
        if self.layout is not None and self.layout not in self.room_layouts():
            self.layout = None

    def set_rated(self, rated: bool) -> None:
        self.rated = rated
        self._build_form()

    def set_seats(self, seats: int) -> None:
        self.seats = seats
        self._settle()
        self._build_form()

    def set_size(self, size: str) -> None:
        self.size = size
        self._settle()
        self._build_form()

    def set_layout(self, layout: Layout | None) -> None:
        if layout is not None and layout not in self.room_layouts():
            return  # not offered for these seats: a click must not silently become Any
        self.layout = layout
        self._settle()
        self._build_form()

    def set_theme(self, theme: MapTheme) -> None:
        self.theme = theme
        self._build_form()

    def set_faction(self, faction: Race) -> None:
        """Your faction, shared by creating and joining: the host's first seat today, every
        seat's ``player_options`` once the framework lands.  Joining never re-chooses after start."""
        self.faction = faction
        self._build_form()

    def toggle_magic(self) -> None:
        self.magic = not self.magic
        self._build_form()

    def create_options(self) -> dict:
        """The room the Create button asks for: a fair map of these settings, the creator first."""
        from warband.ui.scene import fair_map
        width, height = self.room_dimensions()
        layout = self.layout if self.layout in self.room_layouts() else None
        seed, _world = fair_map(mapgen.fresh_seed(), width, height, self.seats, theme=self.theme,
                                races=[self.faction] + [None] * (self.seats - 1), layout=layout, magic=self.magic)
        return {"seed": seed, "width": width, "height": height, "theme": self.theme.value, "players": self.seats,
                "races": [self.faction.value] + [None] * (self.seats - 1),
                "layout": "any" if layout is None else layout.value, "magic": self.magic}

    def create_match(self):
        """The two-seat match a LAN host plays: this panel's map for two, the host first."""
        from warband.online.authority import WarbandMatch
        from warband.ui.scene import fair_map
        sizes = self.online_sizes(2)
        size = self.size if self.size in sizes else sizes[0]
        width, height = mapgen.dimensions(size, 2)
        layouts = mapgen.layouts_for(width, height, 2)
        layout = self.layout if self.layout in layouts else None
        seed, _world = fair_map(mapgen.fresh_seed(), width, height, 2, theme=self.theme,
                                races=[self.faction, None], layout=layout, magic=self.magic)
        return WarbandMatch(seed, width, height, self.theme, races=(self.faction, None), layout=layout, magic=self.magic)

    def create_scene(self, session, match):
        return NetworkGameScene(session, match, settings=self.settings)

    # -- Seams for the ratings-stream framework -------------------------------------

    def player_options(self) -> dict:
        """This seat's options for the room server: the shared faction choice.

        Sent on create and join; never on rejoin, where a seat rejoins rather than re-chooses."""
        return {"race": self.faction.value}

    def _online_kwargs(self, *, for_rejoin: bool = False) -> dict:
        """Extra ``OnlineClient`` kwargs: identity, ``rated`` and ``player_options`` on create
        and join; the stored endpoint identity only on rejoin, never a faction override."""
        if for_rejoin:
            return online_identity(self.game, self.last_room["endpoint"] or None)
        return {**online_identity(self.game), "rated": self.rated, "player_options": self.player_options()}

    # -- Transport: the base lifecycle, through the game-owned lobby ------------------

    # A damaged profile or identity record is already reported on the form; if either
    # helper still fails here, its domain error lands in the message, never a crash —
    # and no invented name or token is substituted.
    _TRANSPORT_ERRORS = (OSError, ValueError, SaveError, SettingsError)

    def host(self):
        try:
            if self.mode == "online":
                from saga2d.online import OnlineClient
                session = OnlineClient(self.game_id, options=self.create_options(), **self._online_kwargs())
                match = None
            else:
                port = self._port()
                match = self.create_match()
                session = MatchHost(self.game_id, match.apply, match.snapshot,
                                    address=("0.0.0.0", port), token=self.fields[2] or None)
                self.fields[2] = session.token
        except self._TRANSPORT_ERRORS as exc:
            self.message = str(exc)
            return
        self.game.push(WarbandLobby(session, lambda connection: self.create_scene(connection, match), title=self.title))

    def join(self):
        try:
            if self.mode == "online":
                if not self.fields[2]:
                    raise ValueError("Enter a room code first.")
                from saga2d.online import OnlineClient
                session = OnlineClient(self.game_id, room=self.fields[2], **self._online_kwargs())
            else:
                port = self._port()
                if not self.fields[0] or not self.fields[2]:
                    raise ValueError("Enter the host address and room code first.")
                session = MatchClient(self.game_id, (self.fields[0], port), token=self.fields[2])
        except self._TRANSPORT_ERRORS as exc:
            self.message = str(exc)
            return
        self.game.push(WarbandLobby(session, lambda connection: self.create_scene(connection, None), title=self.title))

    def rejoin(self):
        from saga2d.online import OnlineClient
        record = self.last_room
        try:
            session = OnlineClient(self.game_id, endpoint=record["endpoint"], room=record["room"],
                                   resume_token=record["resume_token"], **self._online_kwargs(for_rejoin=True))
        except self._TRANSPORT_ERRORS as exc:
            self.message = str(exc)
            return
        self.game.push(WarbandLobby(session, lambda connection: self.create_scene(connection, None), title=self.title))

    def room_code_from_text(self, text: str) -> str | None:
        """The room code *text* names: a bare short code, or the exact public path of an
        ``http(s)`` invite link for this game.  Anything else — another game's path, any
        query string, a long token — is ``None``: a private seat is never a paste."""
        text = text.strip()
        if not text:
            return None
        if "/" in text or "?" in text or "://" in text:
            try:
                parsed = urlsplit(text if "://" in text else "https://" + text.lstrip("/"))
            except ValueError:
                return None
            if parsed.scheme not in ("http", "https"):
                return None
            segments = parsed.path.rstrip("/").split("/")
            if len(segments) != 4 or segments[1] != "join" or segments[2] != self.game_id or not segments[3]:
                return None
            if parsed.query:
                return None  # invite links carry no query; private resume forms hide in one
            code = segments[3]
        else:
            code = text
        if len(code) <= 12 and code.isascii() and code.isalnum():
            return code.upper()
        return None

    def paste_code(self):
        """Take the clipboard's room code or invite link (see :meth:`room_code_from_text`)."""
        code = self.room_code_from_text(self.game.backend.get_clipboard_text())
        if code is None:
            self.message = "Copy the room code — or the whole invite link — then choose Paste invite."
            return
        self.fields[2] = code
        self.focus = 2
        self._replace_field = False
        self.message = ""

    # -- The form --------------------------------------------------------------------

    def _option(self, text: str, selected: bool, on_click, width: int) -> Button:
        """A setting chip: gold when picked, ghost when not — the CTA blue stays on Create/Join."""
        return Button(text, on_click=on_click, style=PICKED_BUTTON if selected else GHOST_BUTTON, width=width)

    def _identity_line(self) -> str:
        if self._profile_error:
            return f"Profile unreadable: {self._profile_error}"
        if self._identity_notice:
            return self._identity_notice
        if self._stored_profile is None:
            return (f"Playing as {self._profile_name} · no online matches yet — "
                    "connect to a room to establish your online rating")
        return (f"Playing as {self._profile_name} · "
                f"online rating {format_rating(self._stored_profile['rating'])} "
                f"over {self._stored_profile['games']} games")

    def _build_form(self):
        self.ui.clear()
        faction = Row(Label("Your faction", text_style="body", width=110), spacing=8)
        for race in Race:
            faction.add(self._option(RACES[race].name, race is self.faction,
                                     lambda r=race: self.set_faction(r), width=118))
        body = self._lan_card() if self.mode == "lan" else Row(self._create_card(), self._join_card(), spacing=16)
        self.ui.add(Column(Label(self.title, text_style="title"),
                           Label(lambda: self._identity_line(), text_style="sub", width=980, wrap=True),
                           faction,
                           body,
                           Row(self._option("Online" + (" · selected" if self.mode == "online" else ""), self.mode == "online",
                                            lambda: self.set_mode("online"), width=250),
                               self._option("LAN · advanced" + (" · selected" if self.mode == "lan" else ""), self.mode == "lan",
                                            lambda: self.set_mode("lan"), width=250),
                               Button("Back", shortcut="Esc", on_click=self.leave, style=MENU_BUTTON, width=160),
                               spacing=12),
                           Label(lambda: self.message, width=980, wrap=True, text_style="sub"),
                           width=1060, spacing=8, anchor=Anchor.CENTER, style=OVERLAY_STYLE))

    def _create_card(self) -> Column:
        card = Column(Label("Create a room", text_style="heading"), spacing=6, margin=0, width=600, style=PANEL_STYLE)
        rated = Row(Label("Room", text_style="body", width=90), spacing=8)
        rated.add(self._option("Rated duel" if self.seats == 2 else "Rated room", self.rated,
                               lambda: self.set_rated(True), width=150))
        rated.add(self._option("Casual room", not self.rated, lambda: self.set_rated(False), width=150))
        card.add(rated)
        card.add(Label("Rated rooms count toward your online rating." if self.rated
                       else "A casual room never changes a rating.", text_style="caption"))
        seats = Row(Label("Seats", text_style="body", width=90), spacing=8)
        for count in ROOM_SEATS:
            seats.add(self._option(str(count), count == self.seats, lambda c=count: self.set_seats(c), width=100))
        card.add(seats)
        sizes = Row(Label("Size", text_style="body", width=90), spacing=8)
        for name in self.online_sizes():
            sizes.add(self._option(name, name == self.size, lambda n=name: self.set_size(n), width=100))
        card.add(sizes)
        # Only the layouts this seat count holds are shown; the rest are omitted, not reset behind a click.
        offered = [None, *self.room_layouts()]
        for first in (0, 3):
            row = Row(Label("Map" if first == 0 else "", text_style="body", width=90), spacing=8)
            for layout in offered[first:first + 3]:
                row.add(self._option("Any" if layout is None else layout.value.title(), layout is self.layout,
                                     lambda chosen=layout: self.set_layout(chosen), width=130))
            card.add(row)
        land = Row(Label("Land", text_style="body", width=90), spacing=8)
        for theme in MapTheme:
            land.add(self._option(theme.value.title(), theme is self.theme,
                                  lambda t=theme: self.set_theme(t), width=130))
        card.add(land)
        self.magic_button = Button("Magic: On" if self.magic else "Magic: Off", on_click=self.toggle_magic,
                                   style=PICKED_BUTTON if self.magic else GHOST_BUTTON, width=220,
                                   tooltip="Choose magic for rooms you create. Joining uses the host's choice.")
        card.add(Row(self.magic_button,
                     Button("Create room", on_click=self.host, style=ACTION_BUTTON, width=220), spacing=8))
        return card

    def _join_card(self) -> Column:
        card = Column(Label("Join a room", text_style="heading"), spacing=6, margin=0, width=380, style=PANEL_STYLE)
        card.add(Button(lambda: f"Code: {self.fields[2] or '(type here)'}", on_click=lambda: self.select_field(2),
                        style=GHOST_BUTTON, width=356))
        card.add(Row(Button("Paste invite", on_click=self.paste_code, style=GHOST_BUTTON, width=170),
                     Button("Join room", shortcut="Enter", on_click=self.join, style=ACTION_BUTTON, width=170),
                     spacing=16))
        if (self.last_room["game_id"] == self.game_id and self.last_room["room"] and self.last_room["resume_token"]):
            card.add(Button(f"Rejoin last room · {self.last_room['room']}", on_click=self.rejoin,
                            style=MENU_BUTTON, width=356))
        card.add(Label("Paste a room code or an invite link, then Enter joins.",
                       text_style="caption", width=356, wrap=True))
        if self.update_check.status == "update":
            latest = self.update_check.latest
            card.add(Button("Open download page", on_click=self.open_download, style=GHOST_BUTTON, width=356))
            card.add(Label(f"Update available: {latest['name']} {latest['version']}",
                           text_style="caption", width=356, wrap=True))
        return card

    def _lan_card(self) -> Column:
        card = Column(Label("LAN · advanced", text_style="heading"), spacing=6, margin=0, width=980, style=PANEL_STYLE)
        names = ("Host address", "Port", "Room code")
        for i in (0, 1, 2):
            card.add(Button(lambda i=i: f"{names[i]}: {self.fields[i] or '(type here)'}",
                            on_click=lambda i=i: self.select_field(i), style=GHOST_BUTTON, width=560))
        self.magic_button = Button("Magic: On" if self.magic else "Magic: Off", on_click=self.toggle_magic,
                                   style=PICKED_BUTTON if self.magic else GHOST_BUTTON, width=220,
                                   tooltip="Choose magic for rooms you host. Joining uses the host's choice.")
        card.add(Row(Button("Host room", on_click=self.host, style=ACTION_BUTTON, width=220),
                     Button("Join room", on_click=self.join, style=GHOST_BUTTON, width=220),
                     self.magic_button, spacing=8))
        card.add(Label("Two seats on one network: the host plays the first. Tab moves between fields; "
                       "your faction and magic above apply to rooms you host.",
                       text_style="caption", width=900, wrap=True))
        return card


class WarbandLobby(MatchLobby):
    """Warband's own waiting room: a gold-and-iron panel over the inherited lifecycle.

    Waiting, private-seat saving, the transition into the match and leaving stay exactly
    the base's, and the invite link never carries the private resume token.  The roster
    names only what the session reports: per-seat lines where the server lists its
    players, an honest connected count where it reports counts alone, and open seats
    where it reports nulls — never an invented opponent."""

    def __init__(self, session, make_scene, *, title="Warband multiplayer"):
        self._identity_saved: object = None
        super().__init__(session, make_scene, title=title)

    def update(self, dt):
        super().update(dt)
        if not _is_online(self.session):
            return
        seen = (self.session.player_token, repr(session_profile(self.session)))
        if seen != self._identity_saved:
            self._identity_saved = seen
            refresh_online_identity(self.game, self.session)

    def _build(self):
        self.ui.clear()
        items: list = [Label(self.title, text_style="title"),
                       Label(lambda: self._status(), text_style="heading")]
        items.extend(self._share_block())
        items.extend([Label(lambda: self._roster_text(), width=560, wrap=True, text_style="body"),
                      Label(lambda: self._rating_line(), width=560, wrap=True, text_style="sub"),
                      Label(lambda: self.session.error, width=560, wrap=True, text_style="sub")])
        if _is_online(self.session):
            if self.session.incompatible:
                items.append(Button("Open download page", on_click=self.open_download, width=280))
            else:
                # Sharing the invite is the waiting room's action: blue primary; the code
                # button and Cancel are quiet.  Attribute names stay the base's: its update
                # enables both buttons once the room is confirmed.
                self.invite_button = Button("Copy invite link", on_click=self.copy_invite,
                                            style=ACTION_BUTTON, width=260, enabled=False)
                self.copy_button = Button("Copy room code", on_click=self.copy_room,
                                          style=GHOST_BUTTON, width=260, enabled=False)
                items.append(Row(self.invite_button, self.copy_button, spacing=16))
        items.append(Button("Cancel", shortcut="Esc", on_click=self.leave, style=GHOST_BUTTON, width=240))
        self.ui.add(Column(*items, width=640, spacing=14, anchor=Anchor.CENTER, style=OVERLAY_STYLE))

    def _share_text(self) -> str:
        """The share line beneath the room code, from the live session alone.

        A confirmed welcome (``state``) names who must connect from the
        authoritative seat count; a named room without one is still joining;
        otherwise the room is still being created."""
        if self.session.state is not None:
            seats = self.session.seats
            who = "both" if seats == 2 else f"all {seats}"
            return f"Share this invite. The match starts when {who} players connect."
        if self.session.room:
            return f"Joining online room {self.session.room}…"
        return "Creating your online room…"

    def _share_block(self) -> list:
        """The room code as a gold banner with one short share line beneath it."""
        from warband.ui.style import GOLD

        if not _is_online(self.session) or self.session.incompatible:
            return [Label(lambda: self._instructions(), width=560, wrap=True, text_style="body")]
        return [Label("Room code", text_style="sub"),
                Label(lambda: self.session.room, text_style="title", text_color=GOLD),
                Label(lambda: self._share_text(), width=560, wrap=True, text_style="body")]

    def _roster_text(self) -> str:
        """Who is here: per-seat lines where the session lists its players in seat order —
        open seats for nulls — or the honest connected count where it reports counts alone."""
        session = self.session
        players = session.players if _is_online(session) else None
        if isinstance(players, list) and players:
            lines = []
            for index, entry in enumerate(players):
                # Server seats are zero-based like session.player; the roster counts from one.
                if not isinstance(entry, dict):
                    lines.append(f"Seat {index + 1}: open — waiting for a player")
                    continue
                seat = entry.get("seat")
                shown = seat + 1 if isinstance(seat, int) else index + 1
                name = entry.get("name") or ("Guest" if not entry.get("player_id") else "Player")
                rating = entry.get("rating")
                line = f"Seat {shown}: {name}"
                if isinstance(rating, (int, float)) and not isinstance(rating, bool):
                    line += f" · {format_rating(rating)}"
                line += " · connected" if entry.get("connected") else " · waiting"
                lines.append(line)
            return "\n".join(lines)
        if _is_online(session):
            return f"{session.present} of {session.seats} seats connected."
        return ""  # LAN details live in the share text above; nothing to count beyond them.

    def _rating_line(self) -> str:
        """This seat's live online rating, or the honest placeholder while none is known."""
        if not _is_online(self.session):
            return ""
        profile = session_profile(self.session)
        if profile is None:
            return "No online matches yet — connect to a room to establish your online rating."
        return f"Online rating {format_rating(profile['rating'])} over {profile['games']} games."


HIT_AUDIO_FIELDS = frozenset({'source_type', 'target_type', 'target_armor', 'target_complete'})
#: The room publishes every other 20 Hz tick: the interval to present over until arrivals have been measured.
SNAPSHOT_INTERVAL = 0.1
#: Units cover what the latest snapshot says a little more slowly than snapshots come, so one that is a little late
#: finds them still moving instead of stopped.
SLACK = 1.25
#: A gap longer than this is a stall, a pause or a resume: what arrives after it is placed, not slid into.
STALL = 0.5
#: Silence this long from a ready room is said on the status line.
QUIET = 1.0


def take_state(old, new) -> None:
    """Make *old* hold everything *new* holds, keeping *old* itself, which the view and the HUD hold.  Through
    ``__getstate__``, which a compiled simulation's objects have and a ``__dict__`` they have not."""
    for name, value in new.__getstate__().items():
        setattr(old, name, value)


def _room_memory(game):
    """What the player had seen of buildings out of sight in the online room they last played.  A room tells a seat
    only what it sees now (WB-011), so rejoining it from the title would otherwise forget the rival's base."""
    return Settings(game.data_dir / 'online-memory.json', {'room': '', 'player': -1, 'seen': {'buildings': []}})


class NetworkGameScene(GameScene):
    #: The match plays on elsewhere; freezing snapshots locally would desync it.
    auto_pause_on_background = False
    #: The room server drops a connection that sends more than 40 orders at once (20 a second after that): cancel mode
    #: and the side's commands give 20 at most between them, and 10 a second, leaving the rest for the player's own.
    order_burst = 20

    def __init__(self, session, match=None, *, settings=None):
        self.session, self.match = session, match
        self._revision = session.revision
        self._event_id = 0
        self._basic_audio_notice = False
        self._network_steps = 0
        self._last_time = time.monotonic()
        self._elapsed = 0.
        self._snapshot_at = 0.0  # scene clock of the latest snapshot
        self._quiet_said = False  # the status line says the server has gone quiet
        self._interval = SNAPSHOT_INTERVAL  # measured time between snapshots, smoothed
        data = session.state
        super().__init__(World.from_dict(data['world']), data['seed'], settings=settings, player=session.player, ranked=False)
        self.brains = []
        self.tutorial = None
        self._autosave_at = math.inf
        self._identity_saved: object = None  # last persisted (player_id, profile, result): saved again on change

    def on_enter(self):
        if _is_online(self.session):
            record = _room_memory(self.game)
            if (record['room'], record['player']) == (self.session.room, self.session.player):
                check_memory(record['seen'], self.world)
                self._seen = record['seen']
        super().on_enter()
        self.every(1 / 60, self._poll)

    def on_close(self):
        if _is_online(self.session) and self.session.room:
            record = _room_memory(self.game)
            record.update(room=self.session.room, player=self.session.player, seen=self.view.memory())
            record.save()
        self.session.close()

    def _step_match(self):
        now = time.monotonic()
        dt, self._last_time = min(.25, now - self._last_time), now
        if self.match is None or not self.session.ready:
            self._elapsed = 0.
            return
        self._elapsed += dt
        while self._elapsed >= SIM_DT:
            self.match.step()
            self._elapsed -= SIM_DT
            self._network_steps += 1
            if self._network_steps % 2 == 0:
                self.session.publish()

    def _advance(self, dt):
        pass  # The host match advances through its scene-owned timer, including under menus.

    def _save_identity(self) -> None:
        """Persist the latest own server token, id, profile and result, so the setup rating
        card stays current when returning from a match.  Only on change: a file write per
        poll would churn."""
        if not _is_online(self.session):
            return
        seen = (self.session.player_token, repr(session_profile(self.session)))
        if seen != self._identity_saved:
            self._identity_saved = seen
            refresh_online_identity(self.game, self.session)

    def _poll(self):
        self.session.poll()
        self._save_identity()
        self._step_match()
        if self.session.error and self.session.ready:
            self.say(self.session.error)
            self.session.error = ""
        if not self.session.ready:
            if _is_online(self.session):
                if self.session.error:
                    self.say(self.session.error)
                elif session_rated(self.session):
                    self.say('Match paused — waiting for your partner to reconnect. '
                             + rated_grace_clause(self.session))
                else:
                    self.say('Match paused — waiting for your partner to reconnect.')
            else:
                self.say('Match paused — waiting for your partner.' if self.session.player == 0 else
                         'Disconnected — return to the title and rejoin the host.')
        elif self.clock - self._snapshot_at > QUIET:
            self.say(f'No word from the server for {self.clock - self._snapshot_at:.0f} s — the match goes on when it answers.')
            self._quiet_said = True
        if self._revision == self.session.revision:
            return
        self._revision = self.session.revision
        if self._quiet_said:  # word came: the silence is over, and the line must not go on saying it
            self.status_timer, self._quiet_said = 0.0, False
        gap = self.clock - self._snapshot_at
        drawn = self.view.drawn_positions() if gap <= STALL else {}  # after a stall or a resume, place; never slide stale motion
        if gap <= STALL:
            self._interval = min(.25, max(.05, .8 * self._interval + .2 * gap))
        self._snapshot_at = self.clock
        data = self.session.state
        fresh = World.from_dict(data['world'])
        for old, new in zip(self.world.players, fresh.players):
            take_state(old, new)
        fresh.players = self.world.players
        take_state(self.world, fresh)
        events = []
        for index, event in data['events']:
            if index > self._event_id:
                if event['kind'] == 'hit':
                    audio_fields = HIT_AUDIO_FIELDS.intersection(event)
                    if not audio_fields:
                        event = {**event, 'source_type': 'unknown', 'target_type': 'unknown'}
                        if not self._basic_audio_notice:
                            self.say('Server uses basic battle audio; update the server for weapon and material sounds.')
                            self._basic_audio_notice = True
                    elif audio_fields != HIT_AUDIO_FIELDS:
                        raise ValueError('Hit event has incomplete battle audio metadata.')
                events.append(Event(**{**event, 'pos': tuple(event['pos'])}))
                self._event_id = index
        self._handle_events(events)
        self._prune_selection()
        self._refresh_card()
        self.view.present_from(drawn)
        self.view.sync(fraction=self._motion_fraction())
        self._check_game_over()

    def _motion_fraction(self):
        """How far units have moved on from where they were drawn towards the latest snapshot."""
        if self._game_over or self.world.winner is not None or not self.player.alive:
            return 1.0
        return min(1.0, (self.clock - self._snapshot_at) / (self._interval * SLACK))

    def order(self, action, *args, **kwargs):
        """Send the order to the match's authority.  One that cannot be sent is refused here and now; what the
        authority refuses comes back later as the session's error."""
        fields = [arg.value if hasattr(arg, 'value') else arg for arg in args]
        try:
            self.session.submit({'action': action, 'args': fields, 'kwargs': kwargs})
        except CommandError as exc:
            raise RuleError(str(exc)) from exc

    def open_menu(self):
        self.game.push(NetworkMenuScene(self))

    def hint(self):
        return [(key, label) for key, label in super().hint() if key != 'F3']

    def _check_game_over(self):
        if self._game_over:
            return
        if self.world.winner is not None or not self.player.alive:
            won = self.world.winner == self.human
            self._finish(won)
            self.game.push(NetworkResultScene(self, won))

    def toggle_pause(self):
        self.say('Online matches continue while menus are open.')

    def save_to(self, slot):
        self.say('This multiplayer match runs live; offline saves are separate.')

    def load_from(self, slot):
        self.say('Use Multiplayer → Rejoin last room to resume online play.' if _is_online(self.session)
                 else 'Rejoin the host to resume this multiplayer match.')


class NetworkMenuScene(_Overlay):
    """A live match menu: local preferences and explicit room departure only."""

    controls = {"s": "settings", "f1": "help", "r": "resign", "t": "leave_match", "q": "quit"}

    def __init__(self, game_scene):
        self.game_scene = game_scene

    def on_enter(self):
        panel = self.panel("Match menu")
        panel.add(Label("The match continues while this menu is open.", text_style="body"))
        session = self.game_scene.session
        if not _is_online(session):
            rejoin = "Rejoin the host from Multiplayer → LAN."
        elif session_rated(session):
            rejoin = rated_grace_clause(session) + " Rejoin from Multiplayer → Rejoin last room."
        else:
            rejoin = "Rejoin from Multiplayer → Rejoin last room."
        panel.add(Label(rejoin, text_style="sub", width=520, wrap=True))
        panel.add(Button("Return to match", hotkey="Esc", on_click=self.game.pop, style=ACTION_BUTTON, width=280))
        panel.add(Button("Settings", hotkey="S", on_click=self.settings, style=GHOST_BUTTON, width=280))
        panel.add(Button("How to play", hotkey="F1", on_click=self.help, style=GHOST_BUTTON, width=280))
        if self._can_resign():
            panel.add(Button("Resign", hotkey="R", on_click=self.resign, style=GHOST_BUTTON, width=280))
        panel.add(Button("Leave match", hotkey="T", on_click=self.leave_match, style=GHOST_BUTTON, width=280))
        panel.add(Button("Quit", hotkey="Q", on_click=self.quit, style=GHOST_BUTTON, width=280))

    def _can_resign(self):
        scene = self.game_scene
        return scene.world.can_resign(scene.human) is None

    def resign(self):
        if self._can_resign():
            self.game.push(ResignScene(self.game_scene))

    def settings(self):
        self.game.push(SettingsScene(self.game_scene))

    def help(self):
        self.game.push(HelpScene(self.game_scene.scheme, magic=self.game_scene.world.magic))

    def leave_match(self):
        from warband.ui.title import TitleScene

        self.game.clear_and_push(TitleScene(settings=self.game_scene.settings))

    def quit(self):
        self.game.quit()


class ResignScene(_Overlay):
    """Resigning online asks first: it cannot be taken back."""

    controls = {("return", "y"): "confirm", ("escape", "n"): "cancel"}

    def __init__(self, game_scene):
        self.game_scene = game_scene

    def on_enter(self):
        world = self.game_scene.world
        panel = self.panel("Resign the match?")
        others = ("Your forces lay down their arms. Your buildings stay, abandoned, and the others fight on."
                  if world.seats >= 3 else "Your forces lay down their arms, and your opponent wins.")
        panel.add(Label(others, text_style="body", width=520, wrap=True))
        panel.add(Button("Resign", hotkey="Enter", on_click=self.confirm, style=ACTION_BUTTON, width=280))
        panel.add(Button("Keep fighting", hotkey="Esc", on_click=self.cancel, style=GHOST_BUTTON, width=280))

    def confirm(self):
        scene = self.game_scene
        self.game.pop()  # this question
        self.game.pop()  # the match menu
        scene.attempt('resign', scene.human)

    def cancel(self):
        self.game.pop()


class NetworkResultScene(NetworkMenuScene):
    """A finished online match leads back to multiplayer, never to a solo rematch.  A player who is out while
    the others fight on may stay and watch."""

    pop_on_cancel = False
    controls = {("t", "escape"): "leave_match", "q": "quit", "w": "watch"}

    def __init__(self, game_scene, won):
        super().__init__(game_scene)
        self.won = won

    def on_enter(self):
        self._decided = self.game_scene.world.winner
        self._build_panel()

    def update(self, dt):
        super().update(dt)
        # An eliminated seat watches on while the others fight: when the match decides under
        # this same overlay, rebuild once — title, receipt and actions — instead of going stale.
        if self._decided is not self.game_scene.world.winner:
            self._decided = self.game_scene.world.winner
            self._build_panel()

    def _build_panel(self):
        scene = self.game_scene
        decided = scene.world.winner is not None
        title = ("Victory!" if self.won else f"Defeat — {self._winner_name(scene)} prevails" if decided
                 else "You are out — the others fight on")
        self.ui.clear()
        panel = self.panel(title)
        stats = scene.stats
        panel.add(Label(f"{_clock(scene.world.time)} played · {stats['units_killed']} kills · "
                        f"{stats['units_lost']} units lost", text_style="body"))
        # Live getter: the authoritative result may arrive after the winner snapshot,
        # so an open result screen changes from waiting to rated without reopening.
        panel.add(Label(lambda: self._rating_text(), text_style="body", width=520, wrap=True))
        panel.add(Label("For another match, choose Multiplayer on the title screen.", text_style="sub"))
        if not decided:
            panel.add(Button("Watch", hotkey="W", on_click=self.watch, style=ACTION_BUTTON, width=280))
        panel.add(Button("Back to title", hotkey="T", on_click=self.leave_match, style=ACTION_BUTTON if decided else GHOST_BUTTON, width=280))
        panel.add(Button("Quit", hotkey="Q", on_click=self.quit, style=GHOST_BUTTON, width=280))

    def watch(self):
        if self.game_scene.world.winner is None:
            self.game.pop()

    def _winner_name(self, scene) -> str:
        """The victor's persistent server name where the roster knows it; world player names
        are faction/team labels, so LAN and roster-less rooms keep those.  No world is mutated."""
        winner = scene.world.winner
        session = scene.session
        if _is_online(session):
            players = session.players
            if isinstance(players, list) and 0 <= winner < len(players):
                entry = players[winner]
                if isinstance(entry, dict) and entry.get("name"):
                    return entry["name"]
        return scene.world.players[winner].name

    def _rating_text(self) -> str:
        """This seat's authoritative rating receipt: before, after and delta for rated rooms.

        Only the server's own result is shown — never the offline skirmish rating, never another
        seat's.  While a rated result is still travelling, the screen honestly waits for it."""
        session = self.game_scene.session
        if not _is_online(session):
            return "A LAN room: no rating changes."
        if not session_rated(session):
            return "A casual room: no rating changes."
        result = session_result(session)
        if result is None:
            return "Waiting for the rating result…"
        player_id = session.player_id
        entries = result.get("ratings") if isinstance(result.get("ratings"), list) else None
        mine = next((e for e in entries or [] if isinstance(e, dict) and e.get("player_id") == player_id), None)
        if mine is None:
            return "Rated room: the result names no entry for this seat."
        return (f"Rated: {format_rating(mine['before'])} → {format_rating(mine['after'])} "
                f"({format_rating(mine['delta'], signed=True)}) over {mine['games']} games.")
