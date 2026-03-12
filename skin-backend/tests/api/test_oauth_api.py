import pytest
from urllib.parse import urlparse, parse_qs
from io import BytesIO

from PIL import Image
import jwt


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
    assert created["is_device_shared_client"] is False

    list_resp = await client.get("/admin/oauth/apps", headers=headers)
    assert list_resp.status_code == 200
    apps = list_resp.json()
    assert any(app["app_id"] == created["app_id"] for app in apps)

    update_resp = await client.put(
        f"/admin/oauth/apps/{created['app_id']}",
        json={
            "client_name": "Forum Login V2",
            "redirect_uri": "https://forum.example.com/oauth/callback2",
            "set_as_device_shared_client": True,
        },
        headers=headers,
    )
    assert update_resp.status_code == 200

    device_settings_resp = await client.get("/admin/oauth/device-settings", headers=headers)
    assert device_settings_resp.status_code == 200
    assert device_settings_resp.json()["shared_client_id"] == created["app_id"]


@pytest.mark.asyncio
async def test_oauth_authorize_and_token_exchange(client, admin_headers, auth_headers):
    admin_h = {"Authorization": admin_headers["Authorization"]}
    user_h = {"Authorization": auth_headers["Authorization"]}

    create_profile_resp = await client.post(
        "/me/profiles",
        json={"name": "OAuthSkinPlayer", "model": "default"},
        headers=user_h,
    )
    assert create_profile_resp.status_code == 200
    profile_id = create_profile_resp.json()["id"]

    skin_file = BytesIO()
    Image.new("RGBA", size=(64, 64), color=(40, 160, 220, 255)).save(skin_file, "png")
    skin_file.seek(0)
    upload_resp = await client.post(
        "/me/textures",
        data={"texture_type": "skin", "note": "OAuth Skin", "is_public": "false", "model": "default"},
        files={"file": ("oauth-skin.png", skin_file, "image/png")},
        headers=user_h,
    )
    assert upload_resp.status_code == 200
    skin_hash = upload_resp.json()["hash"]

    apply_resp = await client.post(
        f"/me/textures/{skin_hash}/apply",
        json={"profile_id": profile_id, "texture_type": "skin"},
        headers=user_h,
    )
    assert apply_resp.status_code == 200

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
            "scope": "userinfo email skin",
        },
    )
    assert check_resp.status_code == 200
    check_data = check_resp.json()
    assert check_data["site_name"]
    assert check_data["requester_name"]
    assert check_data["scope"] == "userinfo email skin"
    assert any(item["key"] == "skin" for item in check_data["scope_items"])

    decision_resp = await client.post(
        "/oauth/authorize/decision",
        json={
            "client_id": app["app_id"],
            "redirect_uri": app["redirect_uri"],
            "state": "s123",
            "scope": "userinfo email skin",
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

    skin_resp = await client.get(
        "/oauth/skin",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
    assert skin_resp.status_code == 200
    assert skin_resp.headers.get("content-type", "").startswith("image/png")
    assert skin_resp.headers.get("x-vskin-profile-id") == profile_id
    assert skin_resp.headers.get("x-vskin-skin-hash") == skin_hash
    assert skin_resp.content


@pytest.mark.asyncio
async def test_oauth_permissions_endpoint(client, admin_headers, auth_headers):
    admin_h = {"Authorization": admin_headers["Authorization"]}
    user_h = {"Authorization": auth_headers["Authorization"]}

    create_resp = await client.post(
        "/admin/oauth/apps",
        json={
            "client_name": "Perm App",
            "redirect_uri": "https://ext.example.com/perm-callback",
        },
        headers=admin_h,
    )
    app = create_resp.json()

    decision_resp = await client.post(
        "/oauth/authorize/decision",
        json={
            "client_id": app["app_id"],
            "redirect_uri": app["redirect_uri"],
            "state": "sperm",
            "scope": "permission",
            "approved": True,
        },
        headers=user_h,
    )
    redirect_url = decision_resp.json()["redirect_url"]
    code = parse_qs(urlparse(redirect_url).query)["code"][0]

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
    token_data = token_resp.json()

    perm_resp = await client.get(
        "/oauth/permissions",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
    assert perm_resp.status_code == 200
    payload = perm_resp.json()
    assert payload.get("user_group") in {"user", "teacher", "admin", "super_admin"}
    assert payload.get("user_group_meta", {}).get("title")


@pytest.mark.asyncio
async def test_oauth_device_flow_and_openid_metadata(client, admin_headers, auth_headers, crypto_fixture):
    admin_h = {"Authorization": admin_headers["Authorization"]}
    user_h = {"Authorization": auth_headers["Authorization"]}

    create_profile_resp = await client.post(
        "/me/profiles",
        json={"name": "DeviceFlowPlayer", "model": "slim"},
        headers=user_h,
    )
    assert create_profile_resp.status_code == 200

    skin_file = BytesIO()
    Image.new("RGBA", size=(64, 64), color=(220, 140, 40, 255)).save(skin_file, "png")
    skin_file.seek(0)
    upload_resp = await client.post(
        "/me/textures",
        data={"texture_type": "skin", "note": "Device Flow Skin", "is_public": "false", "model": "slim"},
        files={"file": ("device-flow-skin.png", skin_file, "image/png")},
        headers=user_h,
    )
    assert upload_resp.status_code == 200
    skin_hash = upload_resp.json()["hash"]

    apply_resp = await client.post(
        f"/me/textures/{skin_hash}/apply",
        json={"profile_id": create_profile_resp.json()["id"], "texture_type": "skin"},
        headers=user_h,
    )
    assert apply_resp.status_code == 200

    create_resp = await client.post(
        "/admin/oauth/apps",
        json={
            "client_name": "USTBL",
            "redirect_uri": "https://oauth.ustb.world/",
            "set_as_device_shared_client": True,
        },
        headers=admin_h,
    )
    assert create_resp.status_code == 200
    app = create_resp.json()

    device_settings_resp = await client.get("/admin/oauth/device-settings", headers=admin_h)
    assert device_settings_resp.status_code == 200
    assert device_settings_resp.json()["shared_client_id"] == app["app_id"]
    assert device_settings_resp.json()["default_redirect_uri"] == "https://oauth.ustb.world/"

    openid_resp = await client.get("/.well-known/openid-configuration")
    assert openid_resp.status_code == 200
    openid_data = openid_resp.json()
    assert openid_data["device_authorization_endpoint"].endswith("/oauth/device/code")
    assert openid_data["token_endpoint"].endswith("/oauth/token")
    assert openid_data["jwks_uri"].endswith("/oauth/jwks")
    assert openid_data["shared_client_id"] == str(app["app_id"])

    janus_openid_resp = await client.get("/api/janus/.well-known/openid-configuration")
    assert janus_openid_resp.status_code == 200
    janus_openid_data = janus_openid_resp.json()
    assert janus_openid_data["issuer"].endswith("/api/janus")
    assert janus_openid_data["token_endpoint"].endswith("/api/janus/oauth/token")
    assert janus_openid_data["device_authorization_endpoint"].endswith("/api/janus/oauth/device/code")
    assert janus_openid_data["shared_client_id"] == str(app["app_id"])

    janus_jwks_resp = await client.get("/api/janus/oauth/jwks")
    assert janus_jwks_resp.status_code == 200
    assert janus_jwks_resp.json()["keys"][0]["alg"] == "RS256"

    metadata_resp = await client.get("/")
    assert metadata_resp.status_code == 200
    assert metadata_resp.json()["meta"]["feature.openid_configuration_url"].endswith("/.well-known/openid-configuration")

    device_code_resp = await client.post(
        "/api/janus/oauth/device/code",
        data={
            "client_id": str(app["app_id"]),
            "scope": "openid offline_access Yggdrasil.PlayerProfiles.Select Yggdrasil.Server.Join",
        },
    )
    assert device_code_resp.status_code == 200
    device_data = device_code_resp.json()
    assert device_data["verification_uri"].endswith("/device")
    assert device_data["verification_uri_complete"].endswith(device_data["user_code"])

    preview_resp = await client.get(
        "/oauth/device/authorize/check",
        params={"user_code": device_data["user_code"]},
    )
    assert preview_resp.status_code == 200
    assert preview_resp.json()["status"] == "pending"

    pending_token_resp = await client.post(
        "/api/janus/oauth/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": str(app["app_id"]),
            "device_code": device_data["device_code"],
        },
    )
    assert pending_token_resp.status_code == 400
    assert pending_token_resp.json()["error"] == "authorization_pending"

    approve_resp = await client.post(
        "/oauth/device/authorize/decision",
        json={
            "user_code": device_data["user_code"],
            "approved": True,
        },
        headers=user_h,
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    token_resp = await client.post(
        "/api/janus/oauth/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": str(app["app_id"]),
            "device_code": device_data["device_code"],
        },
    )
    assert token_resp.status_code == 200
    token_data = token_resp.json()
    assert token_data["token_type"] == "Bearer"
    assert token_data.get("id_token")
    assert token_data.get("refresh_token")

    claims = jwt.decode(
        token_data["id_token"],
        crypto_fixture.private_key.public_key(),
        algorithms=["RS256"],
        audience=str(app["app_id"]),
    )
    assert claims["sub"] == auth_headers["X-User-ID"]
    assert claims["selectedProfile"]["name"] == "DeviceFlowPlayer"
    assert claims["selectedProfile"]["properties"][0]["name"] == "textures"

    jwks_resp = await client.get("/oauth/jwks")
    assert jwks_resp.status_code == 200
    assert jwks_resp.json()["keys"][0]["alg"] == "RS256"

    refresh_resp = await client.post(
        "/api/janus/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": str(app["app_id"]),
            "refresh_token": token_data["refresh_token"],
        },
    )
    assert refresh_resp.status_code == 200
    refreshed = refresh_resp.json()
    assert refreshed["access_token"] != token_data["access_token"]
    assert refreshed.get("id_token")
