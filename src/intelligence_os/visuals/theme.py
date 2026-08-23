"""Design theme and visual palette inspired by dark-tech and threeui design systems."""

from dataclasses import dataclass


@dataclass(frozen=True)
class VisualTheme:
    """Color palette and layout constants for high-end technical graphics."""

    # Canvas & Surfaces
    bg_primary: tuple[int, int, int] = (9, 13, 22)         # #090D16 (Deep Obsidian)
    bg_card: tuple[int, int, int] = (19, 27, 46)          # #131B2E (Card Surface)
    bg_code: tuple[int, int, int] = (13, 19, 33)          # #0D1321 (Code block background)
    border_card: tuple[int, int, int] = (35, 48, 77)      # #23304D (Subtle Slate Border)

    # Accent & Glows (from ThreeUI / modern dev tools)
    accent_cyan: tuple[int, int, int] = (0, 242, 254)      # #00F2FE (Neon Cyan)
    accent_blue: tuple[int, int, int] = (79, 172, 254)     # #4FACFE (Electric Blue)
    accent_emerald: tuple[int, int, int] = (16, 185, 129)  # #10B981 (Evidence Emerald)
    accent_purple: tuple[int, int, int] = (168, 85, 247)   # #A855F7 (Insight Purple)

    # Typography
    text_primary: tuple[int, int, int] = (248, 250, 252)   # #F8FAFC (White/Silver)
    text_secondary: tuple[int, int, int] = (148, 163, 184) # #94A3B8 (Muted Slate)
    text_accent: tuple[int, int, int] = (0, 242, 254)      # #00F2FE (Highlight Cyan)


THEME = VisualTheme()
