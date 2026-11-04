"""Tests for source-stripper URL stripping logic.

Covers the pure-Python parts of `source-stripper.py` without needing a live
Discord connection: find_links, strip_source_indicators, _strip_one, and
_host_matches.

Run with `python3 -m pytest test_source_stripper.py` from repo root (venv).
"""
import importlib.util
import pathlib

import pytest

# The bot lives in source-stripper.py (hyphenated filename, not importable by
# name). Load it explicitly so the tests exercise the real file.
_MODULE_PATH = pathlib.Path(__file__).parent / "source-stripper.py"
_spec = importlib.util.spec_from_file_location("source_stripper", _MODULE_PATH)
_source_stripper = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_source_stripper)
Stripper = _source_stripper.Stripper


def make_stripper(matchers):
    s = Stripper.__new__(Stripper)  # skip discord.Client __init__
    s.domain_matchers = matchers
    return s


def strip(link, matchers):
    return make_stripper(matchers).strip_source_indicators([link])


YOUTUBE = [{"domains": ["youtube.com", "youtu.be"],
            "parameters": ["si", "feature", "pp", "kw", "gclid"]}]
X = [{"domains": ["x.com", "twitter.com", "t.co"],
      "parameters": ["a", "s", "t", "cn", "ref_url", "ref_src", "src",
                      "__twitter_impression", "twclid"]}]


# --- find_links -----------------------------------------------------------

def test_find_links_basic():
    s = make_stripper([])
    assert s.find_links("check https://youtube.com/watch?v=1 and http://x.com/a") == \
        ["https://youtube.com/watch?v=1", "http://x.com/a"]


def test_find_links_strips_trailing_punct():
    s = make_stripper([])
    assert s.find_links("see https://youtube.com/watch?v=1, and (https://x.com) then") == \
        ["https://youtube.com/watch?v=1", "https://x.com"]


def test_find_links_preserves_balanced_parens():
    s = make_stripper([])
    assert s.find_links("wiki https://en.wikipedia.org/wiki/Foo_(bar) x") == \
        ["https://en.wikipedia.org/wiki/Foo_(bar)"]


def test_find_links_case_insensitive_scheme():
    s = make_stripper([])
    assert s.find_links("HTTPS://youtube.com/watch HTTPS://youtube.com/watch") == \
        ["HTTPS://youtube.com/watch"]


def test_find_links_ignores_bare_text_and_dedupes():
    s = make_stripper([])
    assert s.find_links("talking about http in prose, no link here") == []
    assert s.find_links("https://a.com/x https://a.com/x") == ["https://a.com/x"]


def test_find_links_leading_paren():
    s = make_stripper([])
    assert s.find_links("see (https://x.com/status/1?s=20), in parens") == \
        ["https://x.com/status/1?s=20"]


def test_strip_param_case_sensitive_name():
    # param NAMES that differ only by case are distinct; keep exact-name match
    out = strip("https://youtube.com/watch?si=x&SI=y&feature=z", YOUTUBE)
    # 'SI' is not 'si', so it is preserved
    assert out == ["https://youtube.com/watch?SI=y"]


def test_amazon_ref_stripped_tag_preserved():
    # `tag` is an Amazon Associates affiliate ID (attribution, NOT source
    # tracking) so it is preserved; `ref`/`ref_`/`keywords` are click-tracking.
    matchers = [{"domains": ["amazon.com"], "parameters": ["ref", "ref_", "keywords"]}]
    out = strip("https://www.amazon.com/dp/B0X?tag=foo-20&ref_=sr_1_1&keywords=x", matchers)
    assert out == ["https://www.amazon.com/dp/B0X?tag=foo-20"]


def test_reddit_share_id_and_utm():
    matchers = [{"domains": ["reddit.com"], "parameters": ["share_id", "rdt", "utm_source", "utm_medium", "utm_campaign"]}]
    out = strip("https://reddit.com/r/x/comments/1/?share_id=abc&rdt=1&utm_source=share&utm_medium=web", matchers)
    assert out == ["https://reddit.com/r/x/comments/1/"]


# --- strip_source_indicators: variable-length / exact-param stripping -----

def test_strip_x_a_and_s_variable_length():
    out = strip("https://x.com/kuruupdates/status/2115653182814613911?a=uimaJy3bBcbyfnLBrjs&s=20", X)
    assert out == ["https://x.com/kuruupdates/status/2115653182814613911"]


def test_strip_twitter_s_and_t():
    out = strip("https://twitter.com/foo/status/1?s=46&t=anything", X)
    assert out == ["https://twitter.com/foo/status/1"]


def test_strip_youtube_si_variable_length():
    # si is base64url, variable length — the old fixed-length regex missed these
    out = strip("https://youtube.com/watch?v=abc&si=SHORT", YOUTUBE)
    assert out == ["https://youtube.com/watch?v=abc"]


def test_strip_youtube_is_param():
    # `is` is a sibling share-tracking token to `si` on youtu.be share links
    out = strip("https://youtu.be/R_2rNnmac34?is=n7RczX-QJyjtWPOd",
                [{"domains": ["youtu.be", "youtube.com"],
                  "parameters": ["si", "is", "feature", "pp", "kw", "gclid"]}])
    assert out == ["https://youtu.be/R_2rNnmac34"]


def test_strip_youtube_preserves_non_tracking_params():
    out = strip("https://www.youtube.com/watch?v=abc&si=x&feature=share&t=30", YOUTUBE)
    # feature is stripped; v and t (watch time) are kept
    assert out == ["https://www.youtube.com/watch?v=abc&t=30"]


# --- official-domain-variant matching ------------------------------------

def test_subdomain_match_is_allowed():
    # www. / m. / music. subdomains of an official domain are official variants
    assert strip("https://m.youtube.com/watch?v=1&si=x", YOUTUBE) == \
        ["https://m.youtube.com/watch?v=1"]
    assert strip("https://music.youtube.com/watch?v=1&si=x", YOUTUBE) == \
        ["https://music.youtube.com/watch?v=1"]


def test_lookalike_domains_rejected():
    assert strip("https://notyoutube.com/watch?si=x", YOUTUBE) == []
    assert strip("https://youtube.com.evil.net/watch?si=x", YOUTUBE) == []
    # youtube.com embedded in a path of another domain is not a match
    assert strip("https://evil.com/?u=youtube.com&si=x", YOUTUBE) == []


def test_alternate_registration_matches():
    assert strip("https://youtu.be/abc?si=xyz", YOUTUBE) == ["https://youtu.be/abc"]
    assert strip("https://t.co/abc?s=20", X) == ["https://t.co/abc"]


def test_case_insensitive_host():
    assert strip("https://YOUTUBE.COM/watch?si=x", YOUTUBE) == \
        ["https://YOUTUBE.COM/watch"]


# --- no-echo and robustness ----------------------------------------------

def test_no_echo_when_nothing_stripped():
    # param present but not in the strip list -> unchanged -> not returned
    assert strip("https://youtube.com/watch?v=abc", YOUTUBE) == []
    # non-matching domain -> not returned
    assert strip("https://example.com/watch?si=x", YOUTUBE) == []


def test_fragment_preserved():
    out = strip("https://youtube.com/watch?v=abc&si=x#t=30", YOUTUBE)
    assert out == ["https://youtube.com/watch?v=abc#t=30"]


def test_trailing_qmark_cleared():
    # removing the only param must drop the query entirely (no dangling ?)
    out = strip("https://youtube.com/watch?si=x", YOUTUBE)
    assert out == ["https://youtube.com/watch"]


def test_duplicate_params_all_removed():
    out = strip("https://x.com/u/1?t=a&t=b&s=20", X)
    assert out == ["https://x.com/u/1"]


def test_no_query_no_crash():
    assert strip("https://youtube.com/watch", YOUTUBE) == []


def test_malformed_url_no_crash():
    assert strip("https://exa mple.com/watch?si=x", YOUTUBE) == []


def test_non_http_scheme_ignored():
    assert strip("ftp://youtube.com/watch?si=x", YOUTUBE) == []


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
