import pytest
from urllib.parse import urlparse, parse_qs


@pytest.mark.asyncio
async def test_admin_manage_oauth_apps(client, admin_headers):
    headers = {"Authorization": admin_headers["Authorization"]}

    create_resp = await client.post(
        "/admin/oauth/apps",
        json={
            "client_name": "Forum Login",
            "redirect_uri": "https://forum.example.com/oauth/callback",
        },
        headers=headers,
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["app_id"] >= 1
    assert created["client_secret"]

    list_resp = await client.get("/admin/oauth/apps", headers=headers)
    assert list_resp.status_code == 200
    apps = list_resp.json()
    assert any(app["app_id"] == created["app_id"] for app in apps)

    update_resp = await client.put(
        f"/admin/oauth/apps/{created['app_id']}",
        json={
            "client_name": "Forum Login V2",
            "redirect_uri": "https://forum.example.com/oauth/callback2",
        },
        headers=headers,
    )
    assert update_resp.status_code == 200


@pytest.mark.asyncio
async def test_oauth_authorize_and_token_exchange(client, admin_headers, auth_headers):
    admin_h = {"Authorization": admin_headers["Authorization"]}
    user_h = {"Authorization": auth_headers["Authorization"]}

    create_resp = await client.post(
        "/admin/oauth/apps",
        json={
            "client_name": "Ext App",
            "redirect_uri": "https://ext.example.com/callback",
        },
        headers=admin_h,
    )
    assert create_resp.status_code == 200
    app = create_resp.json()

    check_resp = await client.get(
        "/oauth/authorize/check",
        params={
            "client_id": app["app_id"],
            "redirect_uri": app["redirect_uri"],
            "state": "s123",
            "scope": "userinfo email",
        },
    )
    assert check_resp.status_code == 200
    check_data = check_resp.json()
    assert check_data["site_name"]
    assert check_data["requester_name"]
    assert check_data["scope"] == "userinfo email"

    decision_resp = await client.post(
        "/oauth/authorize/decision",
        json={
            "client_id": app["app_id"],
            "redirect_uri": app["redirect_uri"],
            "state": "s123",
            "scope": "userinfo email",
            "approved": True,
        },
        headers=user_h,
    )
    assert decision_resp.status_code == 200
    redirect_url = decision_resp.json()["redirect_url"]

    parsed = urlparse(redirect_url)
    params = parse_qs(parsed.query)
    assert params.get("state") == ["s123"]
    assert "code" in params
    code = params["code"][0]

    token_resp = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": str(app["app_id"]),
            "client_secret": app["client_secret"],
            "redirect_uri": app["redirect_uri"],
        },
    )
    assert token_resp.status_code == 200
    token_data = token_resp.json()
    assert token_data["token_type"] == "Bearer"
    assert token_data.get("access_token")

    userinfo_resp = await client.get(
        "/oauth/userinfo",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
    assert userinfo_resp.status_code == 200
    userinfo = userinfo_resp.json()
    assert userinfo["sub"] == auth_headers["X-User-ID"]
    assert userinfo.get("username")
    assert userinfo.get("avatar_url")
    assert userinfo.get("email")

    profile_resp = await client.get(
        "/oauth/profile",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
    assert profile_resp.status_code == 200
    assert profile_resp.json().get("username")

    avatar_resp = await client.get(
        "/oauth/avatar",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
    assert avatar_resp.status_code == 200
    assert avatar_resp.json().get("avatar_url")

    email_resp = await client.get(
        "/oauth/email",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
    assert email_resp.status_code == 200
    assert email_resp.json().get("email")
