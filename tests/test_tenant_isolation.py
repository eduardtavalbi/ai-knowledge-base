from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_users_cannot_read_update_or_delete_each_others_documents(tenant_client):
    client, active_user, first_user, second_user = tenant_client
    with (
        patch("app.api.documents.generate_embedding", return_value=[0.0] * 384),
        patch("app.api.documents.save_document_chunks", new_callable=AsyncMock),
    ):
        created = await client.post(
            "/documents/",
            json={"title": "Private", "content": "First tenant private content"},
        )
        assert created.status_code == 201
        document_id = created.json()["id"]

        active_user["value"] = second_user
        assert (await client.get("/documents/")).json() == []
        assert (await client.get(f"/documents/{document_id}")).status_code == 404

        update = await client.put(
            f"/documents/{document_id}",
            json={"title": "Stolen", "content": "Attempt to overwrite"},
        )
        assert update.status_code == 404

        deleted = await client.delete(f"/documents/{document_id}")
        assert deleted.status_code == 404

        active_user["value"] = first_user
        still_exists = await client.get(f"/documents/{document_id}")
        assert still_exists.status_code == 200
        assert still_exists.json()["content"] == "First tenant private content"


@pytest.mark.asyncio
async def test_identical_content_is_deduplicated_only_within_same_user(tenant_client):
    client, active_user, first_user, second_user = tenant_client
    payload = {"title": "Same", "content": "Same content in separate accounts"}

    with (
        patch("app.api.documents.generate_embedding", return_value=[0.0] * 384),
        patch("app.api.documents.save_document_chunks", new_callable=AsyncMock),
    ):
        first = await client.post("/documents/", json=payload)
        duplicate_for_first = await client.post("/documents/", json=payload)
        active_user["value"] = second_user
        first_for_second = await client.post("/documents/", json=payload)

    assert first.status_code == 201
    assert duplicate_for_first.status_code == 200
    assert duplicate_for_first.json()["id"] == first.json()["id"]
    assert first_for_second.status_code == 201
    assert first_for_second.json()["id"] != first.json()["id"]
