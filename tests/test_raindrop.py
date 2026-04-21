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
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/collections/childrens",
            json={"result": True, "items": []},
        )
        cols = mock_client.get_collections()
        assert len(cols) == 1
        assert cols[0]["title"] == "Instagram"

    def test_list_collections_includes_children(
        self, httpx_mock, mock_client: RaindropClient
    ) -> None:
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/collections",
            json={"result": True, "items": [{"_id": 1, "title": "Root"}]},
        )
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/collections/childrens",
            json={"result": True, "items": [{"_id": 2, "title": "Child", "parent": {"$id": 1}}]},
        )
        cols = mock_client.get_collections()
        titles = {c["title"] for c in cols}
        assert titles == {"Root", "Child"}

    def test_list_collections_fallback_when_children_endpoint_missing(
        self, httpx_mock, mock_client: RaindropClient
    ) -> None:
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/collections",
            json={"result": True, "items": [{"_id": 1, "title": "Root"}]},
        )
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/collections/childrens",
            status_code=404,
        )
        cols = mock_client.get_collections()
        assert len(cols) == 1
        assert cols[0]["title"] == "Root"

    def test_find_or_create_existing(self, httpx_mock, mock_client: RaindropClient) -> None:
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/collections",
            json={"result": True, "items": [{"_id": 42, "title": "Instagram"}]},
        )
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/collections/childrens",
            json={"result": True, "items": []},
        )
        cid = mock_client.find_or_create_collection("Instagram")
        assert cid == 42

    def test_find_or_create_new(self, httpx_mock, mock_client: RaindropClient) -> None:
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/collections",
            json={"result": True, "items": []},
        )
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/collections/childrens",
            json={"result": True, "items": []},
        )
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/collection",
            json={"result": True, "item": {"_id": 99, "title": "NewCol"}},
        )
        cid = mock_client.find_or_create_collection("NewCol")
        assert cid == 99


class TestCreateCollection:
    def test_creates_root_collection(self, httpx_mock, mock_client: RaindropClient) -> None:
        """Creating a collection without a parent posts just the title."""
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/collection",
            json={"result": True, "item": {"_id": 7, "title": "Flat"}},
        )
        cid = mock_client.create_collection("Flat")
        assert cid == 7

        request = httpx_mock.get_requests()[-1]
        assert b'"parent"' not in request.content

    def test_creates_sub_collection_with_parent(
        self, httpx_mock, mock_client: RaindropClient
    ) -> None:
        """Parent ID is serialized as a nested ``$id`` payload."""
        import json

        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/collection",
            json={"result": True, "item": {"_id": 55, "title": "Tracks"}},
        )
        cid = mock_client.create_collection("Tracks", parent_id=42)
        assert cid == 55

        request = httpx_mock.get_requests()[-1]
        body = json.loads(request.content)
        assert body == {"title": "Tracks", "parent": {"$id": 42}}


class TestFindOrCreateSubCollection:
    def test_reuses_existing_sub_collection(self, httpx_mock, mock_client: RaindropClient) -> None:
        """Return existing sub-collection id without creating a new one."""
        collections = [
            {"_id": 10, "title": "Parent"},
            {"_id": 20, "title": "Tracks", "parent": {"$id": 10}},
        ]
        cid = mock_client.find_or_create_sub_collection(
            "tracks", parent_id=10, collections=collections
        )
        assert cid == 20
        assert httpx_mock.get_requests() == []

    def test_creates_when_parent_differs(self, httpx_mock, mock_client: RaindropClient) -> None:
        """A same-named collection under a different parent is not reused."""
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/collection",
            json={"result": True, "item": {"_id": 77, "title": "Tracks"}},
        )
        collections = [
            {"_id": 10, "title": "Parent"},
            {"_id": 20, "title": "Tracks", "parent": {"$id": 99}},
        ]
        cid = mock_client.find_or_create_sub_collection(
            "Tracks", parent_id=10, collections=collections
        )
        assert cid == 77

    def test_fetches_collections_when_not_provided(
        self, httpx_mock, mock_client: RaindropClient
    ) -> None:
        """Falls back to ``get_collections`` when no list is passed."""
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/collections",
            json={"result": True, "items": [{"_id": 10, "title": "Parent"}]},
        )
        httpx_mock.add_response(
            url="https://api.raindrop.io/rest/v1/collections/childrens",
            json={
                "result": True,
                "items": [{"_id": 21, "title": "Memes", "parent": {"$id": 10}}],
            },
        )
        cid = mock_client.find_or_create_sub_collection("Memes", parent_id=10)
        assert cid == 21
