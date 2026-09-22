from dip_studio.presentation.theme import DARK, LIGHT
from dip_studio.presentation.theme_adapter import stylesheet_for


def test_scrollbars_are_centralized_and_square() -> None:
    for tokens in (DARK, LIGHT):
        stylesheet = stylesheet_for(tokens)
        assert "QScrollBar:vertical" in stylesheet
        assert "QScrollBar:horizontal" in stylesheet
        assert "border-radius: 0;" in stylesheet
        assert "QScrollBar::add-line:vertical" in stylesheet
        assert "QScrollBar::sub-line:horizontal" in stylesheet
        assert f"background: {tokens.border};" in stylesheet
