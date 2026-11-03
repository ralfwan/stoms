"""Shared test setup: every served viewer asks for a token.

Servers started in tests take the token from STOMS_TOKEN, and ``urlopen``
sends it as ``Authorization: token …``, so tests of the API need no login.
Tests of the gate itself use ``bare_opener()``, which sends nothing.
"""

from collections.abc import Iterator
from urllib.request import build_opener, install_opener

import pytest
from web_access_helpers import TEST_TOKEN


@pytest.fixture(autouse=True)
def served_token(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv("STOMS_TOKEN", TEST_TOKEN)
    monkeypatch.delenv("STOMS_TOKEN_FILE", raising=False)
    opener = build_opener()
    opener.addheaders = [("Authorization", f"token {TEST_TOKEN}")]
    install_opener(opener)
    yield TEST_TOKEN
    install_opener(None)  # type: ignore[arg-type]
