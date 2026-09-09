"""Warband's look: a dark iron-and-parchment HUD with gold accents; hotkeys as keycaps."""

from __future__ import annotations

from saga2d import Style, TextStyle, Theme, fonts

Color = tuple[int, int, int, int]

GOLD: Color = (255, 214, 110, 255)
LUMBER: Color = (196, 150, 96, 255)
TEXT: Color = (242, 238, 230, 255)
BODY: Color = (222, 218, 210, 255)
MUTED: Color = (172, 168, 160, 255)
DIM: Color = (130, 126, 120, 255)
GOOD: Color = (130, 225, 140, 255)
BAD: Color = (240, 130, 110, 255)
PANEL_BG: Color = (22, 20, 24, 228)
HAIRLINE: Color = (255, 255, 255, 34)
SELECT: Color = (120, 255, 140, 255)
ENEMY: Color = (255, 90, 80, 255)

PANEL_STYLE = Style(background_color=PANEL_BG, border_color=HAIRLINE, border_width=1, padding=12, radius=10)
OVERLAY_STYLE = Style(background_color=(22, 20, 24, 244), border_color=HAIRLINE, border_width=1, padding=22, radius=14)
RESULTS_STYLE = Style(background_color=(22, 20, 24, 255), border_color=HAIRLINE, border_width=1, padding=22, radius=14)
GHOST_BUTTON = Style(font=fonts.SEMIBOLD, background_color=(255, 255, 255, 20), hover_color=(255, 255, 255, 46), press_color=(255, 255, 255, 84),
                     border_color=(255, 255, 255, 40), border_width=1, padding=7, radius=7)
ACTION_BUTTON = Style(font=fonts.SEMIBOLD, background_color=(70, 118, 200, 255), hover_color=(96, 146, 230, 255), press_color=(150, 190, 255, 255),
                      border_color=(150, 195, 255, 110), border_width=1, padding=7, radius=7)
DANGER_BUTTON = Style(font=fonts.SEMIBOLD, background_color=(190, 66, 58, 255), hover_color=(216, 92, 82, 255), press_color=(255, 140, 130, 255),
                      border_color=(255, 150, 140, 110), border_width=1, padding=7, radius=7)
MENU_BUTTON = Style(font=fonts.SEMIBOLD, background_color=(34, 30, 36, 235), hover_color=(58, 52, 60, 255), press_color=(96, 86, 100, 255),
                    border_color=(255, 255, 255, 50), border_width=1, padding=10, radius=10)
CARD_BUTTON = Style(font=fonts.SEMIBOLD, font_size=14, background_color=(255, 255, 255, 22), hover_color=(255, 255, 255, 52), press_color=(255, 255, 255, 90),
                    border_color=(255, 255, 255, 44), border_width=1, padding=6, radius=7)


def build_theme() -> Theme:
    return Theme(
        font=fonts.REGULAR, font_size=15, text_color=TEXT,
        panel_background_color=PANEL_BG, panel_border_color=HAIRLINE, panel_border_width=1, panel_padding=12, panel_radius=10,
        button_background_color=(255, 255, 255, 20), button_hover_color=(255, 255, 255, 46), button_press_color=(255, 255, 255, 84),
        button_disabled_color=(255, 255, 255, 8), button_text_color=TEXT, button_disabled_text_color=(255, 255, 255, 80),
        button_padding=7, button_font_size=14, button_min_width=84, button_radius=7,
        keycap_color=(255, 255, 255, 40), keycap_text_color=TEXT, keycap_font=fonts.SEMIBOLD, keycap_font_size=11,
        progressbar_color=GOLD, progressbar_bg_color=(0, 0, 0, 120),
        text_styles={
            "title": TextStyle(22, GOLD, fonts.EXTRABOLD),
            "heading": TextStyle(17, TEXT, fonts.SEMIBOLD),
            "hud": TextStyle(16, TEXT, fonts.SEMIBOLD),
            "body": TextStyle(14, BODY, fonts.REGULAR),
            "sub": TextStyle(13, MUTED, fonts.REGULAR),
            "caption": TextStyle(12, DIM, fonts.REGULAR),
            "banner": TextStyle(40, (255, 255, 255, 255), fonts.EXTRABOLD),
            "banner_sub": TextStyle(17, (255, 255, 255, 255), fonts.SEMIBOLD),
            "hero": TextStyle(92, GOLD, fonts.EXTRABOLD),
            "hero_sub": TextStyle(19, (224, 218, 208, 255), fonts.REGULAR),
            "floating": TextStyle(16, (255, 255, 255, 255), fonts.EXTRABOLD),
        },
    )
