"""Segment casing engine: analyze/render round-trips, splice_span, render_like."""
from __future__ import annotations

import pytest

from ghostc.aliasing import analyze, render, render_like, splice_span


def roundtrip(token: str) -> str:
    segs, style = analyze(token)
    return render([s.text for s in segs], style)


@pytest.mark.parametrize("token", [
    "booking-core", "BOOKING_CORE_URL", "bookingCore", "BookingCore",
    "booking.core", "bookingcore", "BOOKINGCORE", "Northwind", "SkyRoute",
    "booking core", "region-a", "host-a.example",
])
def test_analyze_render_roundtrip(token):
    assert roundtrip(token) == token


def test_analyze_segments_are_lowercased_with_spans():
    segs, style = analyze("BOOKING_CORE_URL")
    assert [s.text for s in segs] == ["booking", "core", "url"]
    assert style.sep == "_" and style.case == "upper"
    assert "BOOKING_CORE_URL"[segs[1].start:segs[1].end] == "CORE"


@pytest.mark.parametrize("token, expected", [
    ("skyroute", (0, 8, "vendor-a")),                     # bare lower run -> '-' joiner
    ("SKYROUTE_API_KEY", (0, 8, "VENDOR_A")),             # snake/upper keeps separator
    ("northwindSkyrouteConnector", (9, 17, "VendorA")),   # mid-camel, leading cap preserved
    ("northwind-skyroute-connector", (10, 18, "vendor-a")),
])
def test_splice_span_recases_in_place(token, expected):
    assert splice_span(token, ["skyroute"], ["vendor", "a"]) == expected


def test_splice_span_returns_none_when_stem_absent():
    assert splice_span("bookingCore", ["skyroute"], ["vendor", "a"]) is None


def test_splice_span_matches_only_contiguous_runs():
    # "sky" then "route" split by another segment is not the "skyroute" stem
    assert splice_span("skyXroute", ["skyroute"], ["vendor", "a"]) is None


@pytest.mark.parametrize("sample, expected", [
    ("SkyRoute", "VendorA"),
    ("skyroute", "vendor-a"),
    ("SKYROUTE", "VENDOR-A"),
    ("Sky Route", "Vendor A"),
])
def test_render_like_follows_sample_casing(sample, expected):
    assert render_like(sample, ["vendor", "a"]) == expected


def test_render_bare_multiseg_inserts_hyphen():
    _, lower = analyze("skyroute")
    assert render(["vendor", "a"], lower) == "vendor-a"
    _, upper = analyze("SKYROUTE")
    assert render(["vendor", "a"], upper) == "VENDOR-A"
