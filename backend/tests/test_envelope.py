"""Unit tests for the response envelope every ARGUS endpoint returns
(app/models/envelope.py) — pins the contract the frontend's fetch layer
relies on."""

from app.models.envelope import Envelope, Meta


def test_meta_defaults():
    meta = Meta()
    assert meta.total == 0
    assert meta.page == 1
    assert meta.page_size == 50


def test_envelope_wraps_arbitrary_data_without_meta():
    envelope = Envelope[dict](data={"id": "PRS-0000001"})
    assert envelope.data == {"id": "PRS-0000001"}
    assert envelope.meta is None
    assert envelope.error is None


def test_envelope_with_pagination_meta():
    envelope = Envelope[list](data=[1, 2, 3], meta=Meta(total=100, page=2, page_size=3))
    assert envelope.meta is not None
    assert envelope.meta.total == 100
    assert len(envelope.data) == 3
