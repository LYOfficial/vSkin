import pytest
from fastapi import HTTPException
from backends.admin_backend import AdminBackend

@pytest.mark.asyncio
async def test_admin_settings_management(db_session, test_config):
    """测试管理员对设置的分组管理逻辑"""
    backend = AdminBackend(db_session, test_config)
    
    # 1. 保存站点设置
    site_settings = {
        "site_name": "New Test Site",
        "allow_register": False,
        "max_texture_size": 2048
    }
    await backend.save_settings_group("site", site_settings)
    
    # 验证保存结果
    fetched = await backend.get_site_settings()
    assert fetched["site_name"] == "New Test Site"
    assert fetched["allow_register"] is False
    assert fetched["max_texture_size"] == 2048
    
    # 2. 保存安全设置
    security_settings = {
        "rate_limit_enabled": True,
        "rate_limit_auth_attempts": 10
    }
    await backend.save_settings_group("security", security_settings)
    assert (await backend.get_security_settings())["rate_limit_auth_attempts"] == 10

    janus_settings = {
        "janus_enabled": True,
        "janus_base_path": "api/janus",
        "janus_union_mode": "excludes",
        "janus_union_code": "ABC_DEF",
    }
    await backend.save_settings_group("janus", janus_settings)
    janus_fetched = await backend.get_janus_settings()
    assert janus_fetched["janus_enabled"] is True
    assert janus_fetched["janus_base_path"] == "/api/janus"
    assert janus_fetched["janus_union_mode"] == "excludes"
    assert janus_fetched["janus_union_code"] == "ABC_DEF"

@pytest.mark.asyncio
async def test_admin_user_controls(db_session, test_config, user_factory):
    """测试管理员对用户的管控逻辑：列表、封禁、删除、权限切换"""
    backend = AdminBackend(db_session, test_config)
    admin = await user_factory(is_admin=True, username="AdminUser")
    await db_session.user.set_user_group(admin.id, "super_admin")
    user = await user_factory(is_admin=False, username="NormalUser")
    
    # 1. 获取用户列表
    user_list = await backend.get_admin_users()
    assert len(user_list) == 2
    
    # 2. 封禁用户 (先对普通用户操作)
    import time
    banned_until = int((time.time() + 3600) * 1000)
    await backend.ban_user(user.id, banned_until, admin.id)
    assert await db_session.user.is_banned(user.id) is True

    # 3. 切换管理员状态
    await backend.toggle_user_admin(user.id, admin.id)
    assert (await db_session.user.get_by_id(user.id)).is_admin == 1
    assert (await db_session.user.get_by_id(user.id)).user_group == "admin"

    # 禁止取消自己的管理员
    with pytest.raises(HTTPException) as exc:
        await backend.toggle_user_admin(admin.id, admin.id)
    assert exc.value.status_code == 403

    # 4. 降级并删除用户
    await backend.toggle_user_admin(user.id, admin.id) # 降级回普通用户
    assert (await db_session.user.get_by_id(user.id)).is_admin == 0
    assert (await db_session.user.get_by_id(user.id)).user_group == "user"

    await backend.delete_user(user.id, is_admin_action=True)
    assert await db_session.user.get_by_id(user.id) is None


@pytest.mark.asyncio
async def test_only_super_admin_can_assign_admin(db_session, test_config, user_factory):
    backend = AdminBackend(db_session, test_config)
    admin_actor = await user_factory(is_admin=True, username="AdminActor")
    normal_user = await user_factory(is_admin=False, username="NormalUser")

    with pytest.raises(HTTPException) as exc:
        await backend.set_user_group(normal_user.id, admin_actor.id, "admin")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_super_admin_can_refresh_own_group(db_session, test_config, user_factory):
    backend = AdminBackend(db_session, test_config)
    super_admin = await user_factory(is_admin=True, username="RootUser")
    await db_session.user.set_user_group(super_admin.id, "super_admin")

    await backend.set_user_group(super_admin.id, super_admin.id, "super_admin")
    row = await db_session.user.get_by_id(super_admin.id)
    assert row.user_group == "super_admin"
    assert row.is_admin == 1



@pytest.mark.asyncio
async def test_admin_invite_code_creation(db_session, test_config):
    """测试邀请码生成逻辑"""
    backend = AdminBackend(db_session, test_config)
    
    # 1. 自动生成随机码
    code1 = await backend.create_invite(code=None, total_uses=10, note="auto-gen")
    assert len(code1) > 10
    
    # 2. 指定自定义码
    code2 = await backend.create_invite(code="MY_CUSTOM_CODE", total_uses=5)
    assert code2 == "MY_CUSTOM_CODE"
    
    # 3. 格式校验 (太短)
    with pytest.raises(HTTPException) as exc:
        await backend.create_invite(code="123", total_uses=1)
    assert exc.value.status_code == 400
