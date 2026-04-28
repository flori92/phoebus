from unittest.mock import patch

from PHOEBUS.media import recommander_media


def test_recommander_media_ouvre_justwatch_et_propose_fallback():
    with (
        patch("PHOEBUS.media.open_uri") as mock_open,
        patch("PHOEBUS.media._search_suggestions", return_value=[]),
    ):
        result = recommander_media(kind="film", genre="comedie")

    mock_open.assert_called_once()
    opened_url = mock_open.call_args.args[0]
    assert opened_url.startswith("https://www.justwatch.com/fr/recherche")
    assert "film+comique" in opened_url
    assert "Propositions rapides" in result


def test_recommander_media_respecte_plateforme_netflix():
    with (
        patch("PHOEBUS.media.open_uri") as mock_open,
        patch("PHOEBUS.media._search_suggestions", return_value=["Film A", "Film B"]),
    ):
        result = recommander_media(kind="serie", genre="thriller", platform="netflix")

    assert mock_open.call_args.args[0].startswith("https://www.netflix.com/search")
    assert "Film A" in result
