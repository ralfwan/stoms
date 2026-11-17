"""The token every served viewer in the tests uses (see conftest.py)."""

from urllib.request import HTTPRedirectHandler, OpenerDirector, build_opener

TEST_TOKEN = "test-token-0123456789-abcdefghijklmnopqrstuvwxyz"


class _NoRedirect(HTTPRedirectHandler):
    """Leave redirects (the login's 303) to the test."""

    def redirect_request(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return None


def bare_opener(follow_redirects: bool = False) -> OpenerDirector:
    """An opener without the token (and, by default, without redirects)."""
    if follow_redirects:
        return build_opener()
    return build_opener(_NoRedirect)
