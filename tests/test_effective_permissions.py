"""Cálculo puro de permisos efectivos en un canal (app.core.permissions)."""

from app.core.permissions import ALL_PERMISSIONS, DEFAULT_ROLE_PERMISSIONS, Permission, effective_channel_permissions

VIEW = Permission.VIEW_CHANNELS.value
SEND = Permission.SEND_MESSAGES.value
CONNECT = Permission.CONNECT.value


def calc(role_bitmasks, role_overrides=(), member_overrides=()):
    return effective_channel_permissions(
        role_bitmasks=list(role_bitmasks),
        role_overrides=list(role_overrides),
        member_overrides=list(member_overrides),
    )


def test_all_permissions_includes_every_flag():
    for permission in Permission:
        assert ALL_PERMISSIONS & permission.value


def test_without_roles_has_no_permissions():
    assert calc([]) == 0


def test_roles_are_combined():
    assert calc([VIEW, SEND]) == VIEW | SEND


def test_administrator_has_everything_even_with_channel_deny():
    result = calc([Permission.ADMINISTRATOR.value], member_overrides=[(0, VIEW | SEND)])
    assert result == ALL_PERMISSIONS


def test_role_override_denies_and_allows():
    result = calc([VIEW | SEND], role_overrides=[(CONNECT, SEND)])
    assert result == VIEW | CONNECT


def test_member_override_wins_over_role_override():
    # El rol niega VIEW en el canal, pero una regla del propio miembro lo vuelve a permitir
    result = calc([int(DEFAULT_ROLE_PERMISSIONS)], role_overrides=[(0, VIEW)], member_overrides=[(VIEW, 0)])
    assert result & VIEW


def test_member_deny_wins_over_role_allow():
    result = calc([0], role_overrides=[(SEND, 0)], member_overrides=[(0, SEND)])
    assert not result & SEND


def test_overrides_of_several_roles_are_combined():
    result = calc([VIEW], role_overrides=[(SEND, 0), (CONNECT, 0)])
    assert result == VIEW | SEND | CONNECT
