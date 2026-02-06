"""Tests for the Raindrop.io API client."""

from __future__ import annotations

import pytest

from ig2raindrop_cli.models import InstagramSavedItem, RaindropCreatePayload
from ig2raindrop_cli.raindrop import RaindropClient


@pytest.fixture
def mock_client(httpx_mock) -> RaindropClient:  # noqa: ARG001
    """A RaindropClient with mocked HTTP responses."""
    return RaindropClient(token="test-token-123")


class TestTestConnection:
    def test_success(self, httpx_mock, mock_client: RaindropClient) -> None:
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/user",
            json={"result": True, "user": {"_id": 1}},
        )
        assert mock_client.test_connection() is True

    def test_failure(self, httpx_mock, mock_client: RaindropClient) -> None:
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/user",
            status_code=401,
        )
        assert mock_client.test_connection() is False


class TestCreateRaindrop:
    def test_creates_single(self, httpx_mock, mock_client: RaindropClient) -> None:
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/raindrop",
            json={"result": True, "item": {"_id": 99, "link": "https://example.com"}},
        )
        item = InstagramSavedItem(href="https://example.com", title="Test")
        payload = RaindropCreatePayload.from_instagram_item(item)
        resp = mock_client.create_raindrop(payload)
        assert resp.result is True


class TestImportItems:
    def test_batch_import(self, httpx_mock, mock_client: RaindropClient) -> None:
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/raindrops",
            json={"result": True, "items": [{"_id": 1}, {"_id": 2}]},
        )
        items = [
            InstagramSavedItem(href="https://example.com/1"),
            InstagramSavedItem(href="https://example.com/2"),
        ]
        result = mock_client.import_items(items, batch=True)
        assert result.created == 2
        assert result.failed == 0

    def test_single_import(self, httpx_mock, mock_client: RaindropClient) -> None:
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/raindrop",
            json={"result": True, "item": {"_id": 1}},
        )
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/raindrop",
            json={"result": True, "item": {"_id": 2}},
        )
        items = [
            InstagramSavedItem(href="https://example.com/1"),
            InstagramSavedItem(href="https://example.com/2"),
        ]
        result = mock_client.import_items(items, batch=False)
        assert result.created == 2

    def test_empty_items(self, mock_client: RaindropClient) -> None:
        result = mock_client.import_items([])
        assert result.total == 0
        assert result.created == 0


class TestGetCollections:
    def test_list_collections(self, httpx_mock, mock_client: RaindropClient) -> None:
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/collections",
            json={"result": True, "items": [{"_id": 1, "title": "Instagram"}]},
        )
        cols = mock_client.get_collections()
        assert len(cols) == 1
        assert cols[0]["title"] == "Instagram"

    def test_find_or_create_existing(self, httpx_mock, mock_client: RaindropClient) -> None:
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/collections",
            json={"result": True, "items": [{"_id": 42, "title": "Instagram"}]},
        )
        cid = mock_client.find_or_create_collection("Instagram")
        assert cid == 42

    def test_find_or_create_new(self, httpx_mock, mock_client: RaindropClient) -> None:
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/collections",
            json={"result": True, "items": []},
        )
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/collection",
            json={"result": True, "item": {"_id": 99, "title": "NewCol"}},
        )
        cid = mock_client.find_or_create_collection("NewCol")
        assert cid == 99
