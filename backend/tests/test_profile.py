# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.


def test_profile_partial_updates_accumulate(auth_client):
    # Each onboarding step sends a partial PUT; fields must accumulate, not reset.
    auth_client.put("/api/v1/profile", json={"household_type": "family"})
    auth_client.put("/api/v1/profile", json={"reasons_leaving": ["politics", "cost"]})
    auth_client.put("/api/v1/profile", json={"climate_pref": "warm", "budget_monthly": 2500})

    profile = auth_client.get("/api/v1/profile").json()
    assert profile["household_type"] == "family"
    assert profile["reasons_leaving"] == ["politics", "cost"]
    assert profile["climate_pref"] == "warm"
    assert profile["budget_monthly"] == 2500


def test_profile_requires_auth(client):
    assert client.get("/api/v1/profile").status_code == 401
