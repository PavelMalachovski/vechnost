"""Game logic for the Vechnost bot."""

import random

from .models import GameData, SessionState, Theme


def load_game_data() -> GameData:
    """Load game data from YAML file."""
    from pathlib import Path

    import yaml

    yaml_path = Path(__file__).parent.parent / "data" / "questions.yaml"

    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # Convert string keys to Theme enum
    themes = {}
    for theme_name, theme_data in data.get("themes", {}).items():
        try:
            theme = Theme(theme_name)
            themes[theme] = theme_data
        except ValueError:
            # Skip unknown themes
            continue

    return GameData(themes=themes)


def draw_card(
    session: SessionState,
    game_data: GameData
) -> str | None:
    """Draw a random card that hasn't been drawn yet."""
    if not session.theme or not session.level:
        return None

    available_content = game_data.get_content(
        session.theme,
        session.level,
        session.content_type
    )

    if not available_content:
        return None

    # Filter out already drawn cards
    undrawn_cards = [card for card in available_content if card not in session.drawn_cards]

    if not undrawn_cards:
        return None

    # Draw a random card
    drawn_card = random.choice(undrawn_cards)
    session.drawn_cards.add(drawn_card)

    return drawn_card


def get_remaining_cards_count(session: SessionState, game_data: GameData) -> int:
    """Get the number of remaining cards for the current session."""
    if not session.theme or not session.level:
        return 0

    available_content = game_data.get_content(
        session.theme,
        session.level,
        session.content_type
    )

    if not available_content:
        return 0

    undrawn_cards = [card for card in available_content if card not in session.drawn_cards]
    return len(undrawn_cards)


def can_draw_card(session: SessionState, game_data: GameData) -> bool:
    """Check if a card can be drawn in the current session."""
    return get_remaining_cards_count(session, game_data) > 0


def is_session_complete(session: SessionState, game_data: GameData) -> bool:
    """Check if the current session is complete (no more cards to draw)."""
    return not can_draw_card(session, game_data)


def validate_session(session: SessionState, game_data: GameData) -> bool:
    """Validate that the current session state is valid."""
    if not session.theme or not session.level:
        return False

    # Check if theme exists
    if session.theme not in game_data.themes:
        return False

    # Check if levels exist for theme
    if "levels" not in game_data.themes[session.theme]:
        return False

    # Check if level exists for theme
    if session.level not in game_data.themes[session.theme]["levels"]:
        return False

    # Check if content type is available
    available_types = game_data.get_available_content_types(session.theme, session.level)
    if session.content_type not in available_types:
        return False

    return True
