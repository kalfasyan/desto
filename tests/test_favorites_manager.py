"""Tests for FavoriteCommandsManager."""

import os

import pytest

from desto.redis.client import DestoRedisClient
from desto.redis.favorites_manager import FavoriteCommandsManager

pytestmark = pytest.mark.skipif(os.getenv("CI") == "true", reason="Redis is not available on GitHub Actions")


@pytest.fixture
def redis_client():
    """Create a Redis client for testing."""
    config = {
        "host": "localhost",
        "port": 6379,
        "db": 1,
        "enabled": True,
        "connection_timeout": 5,
    }
    client = DestoRedisClient(config)
    yield client
    # Cleanup: delete all test favorites
    if client.redis:
        client.redis.flushdb()


@pytest.fixture
def favorites_manager(redis_client):
    """Create a FavoriteCommandsManager instance."""
    return FavoriteCommandsManager(redis_client)


def test_add_favorite(favorites_manager):
    """Test adding a new favorite command."""
    favorite = favorites_manager.add_favorite(name="test_script", command="python test.py --arg1 value1")

    assert favorite is not None
    assert favorite.name == "test_script"
    assert favorite.command == "python test.py --arg1 value1"
    assert favorite.use_count == 0
    assert favorite.created_at is not None
    assert favorite.last_used_at is None


def test_add_duplicate_favorite(favorites_manager):
    """Test that adding a duplicate favorite name returns None."""
    favorites_manager.add_favorite("duplicate", "command1")
    result = favorites_manager.add_favorite("duplicate", "command2")

    assert result is None


def test_list_favorites_empty(favorites_manager):
    """Test listing favorites when none exist."""
    favorites = favorites_manager.list_favorites()
    assert favorites == []


def test_list_favorites_sorted_by_created_at(favorites_manager):
    """Test listing favorites sorted by creation time."""
    favorites_manager.add_favorite("first", "cmd1")
    favorites_manager.add_favorite("second", "cmd2")
    favorites_manager.add_favorite("third", "cmd3")

    favorites = favorites_manager.list_favorites(sort_by="created_at")

    # Should be in reverse chronological order (newest first)
    assert len(favorites) == 3
    assert favorites[0].name == "third"
    assert favorites[1].name == "second"
    assert favorites[2].name == "first"


def test_list_favorites_sorted_by_use_count(favorites_manager):
    """Test listing favorites sorted by use count."""
    favorites_manager.add_favorite("low_use", "cmd1")
    fav2 = favorites_manager.add_favorite("high_use", "cmd2")
    fav3 = favorites_manager.add_favorite("medium_use", "cmd3")

    # Increment usage
    favorites_manager.increment_usage(fav2.favorite_id)
    favorites_manager.increment_usage(fav2.favorite_id)
    favorites_manager.increment_usage(fav2.favorite_id)
    favorites_manager.increment_usage(fav3.favorite_id)

    favorites = favorites_manager.list_favorites(sort_by="use_count")

    # Should be sorted by use count (highest first)
    assert len(favorites) == 3
    assert favorites[0].name == "high_use"
    assert favorites[0].use_count == 3
    assert favorites[1].name == "medium_use"
    assert favorites[1].use_count == 1
    assert favorites[2].name == "low_use"
    assert favorites[2].use_count == 0


def test_list_favorites_sorted_by_name(favorites_manager):
    """Test listing favorites sorted alphabetically by name."""
    favorites_manager.add_favorite("zebra", "cmd1")
    favorites_manager.add_favorite("alpha", "cmd2")
    favorites_manager.add_favorite("beta", "cmd3")

    favorites = favorites_manager.list_favorites(sort_by="name")

    assert len(favorites) == 3
    assert favorites[0].name == "alpha"
    assert favorites[1].name == "beta"
    assert favorites[2].name == "zebra"


def test_get_favorite_by_id(favorites_manager):
    """Test retrieving a favorite by ID."""
    added = favorites_manager.add_favorite("test", "cmd")
    retrieved = favorites_manager.get_favorite(added.favorite_id)

    assert retrieved is not None
    assert retrieved.favorite_id == added.favorite_id
    assert retrieved.name == "test"
    assert retrieved.command == "cmd"


def test_get_favorite_by_id_not_found(favorites_manager):
    """Test retrieving a non-existent favorite returns None."""
    result = favorites_manager.get_favorite("nonexistent-id")
    assert result is None


def test_get_favorite_by_name(favorites_manager):
    """Test retrieving a favorite by name."""
    added = favorites_manager.add_favorite("my_favorite", "echo hello")
    retrieved = favorites_manager.get_favorite_by_name("my_favorite")

    assert retrieved is not None
    assert retrieved.favorite_id == added.favorite_id
    assert retrieved.name == "my_favorite"


def test_get_favorite_by_name_not_found(favorites_manager):
    """Test retrieving a non-existent favorite by name returns None."""
    result = favorites_manager.get_favorite_by_name("nonexistent")
    assert result is None


def test_delete_favorite(favorites_manager):
    """Test deleting a favorite."""
    favorite = favorites_manager.add_favorite("to_delete", "cmd")
    result = favorites_manager.delete_favorite(favorite.favorite_id)

    assert result is True

    # Verify it's deleted
    assert favorites_manager.get_favorite(favorite.favorite_id) is None
    assert favorites_manager.get_favorite_by_name("to_delete") is None
    assert len(favorites_manager.list_favorites()) == 0


def test_delete_favorite_not_found(favorites_manager):
    """Test deleting a non-existent favorite returns False."""
    result = favorites_manager.delete_favorite("nonexistent-id")
    assert result is False


def test_update_favorite_name(favorites_manager):
    """Test updating a favorite's name."""
    favorite = favorites_manager.add_favorite("old_name", "cmd")
    updated = favorites_manager.update_favorite(favorite.favorite_id, name="new_name")

    assert updated is not None
    assert updated.name == "new_name"
    assert updated.command == "cmd"

    # Verify name index is updated
    assert favorites_manager.get_favorite_by_name("new_name") is not None
    assert favorites_manager.get_favorite_by_name("old_name") is None


def test_update_favorite_command(favorites_manager):
    """Test updating a favorite's command."""
    favorite = favorites_manager.add_favorite("test", "old_cmd")
    updated = favorites_manager.update_favorite(favorite.favorite_id, command="new_cmd")

    assert updated is not None
    assert updated.name == "test"
    assert updated.command == "new_cmd"


def test_update_favorite_both(favorites_manager):
    """Test updating both name and command."""
    favorite = favorites_manager.add_favorite("old", "old_cmd")
    updated = favorites_manager.update_favorite(favorite.favorite_id, name="new", command="new_cmd")

    assert updated is not None
    assert updated.name == "new"
    assert updated.command == "new_cmd"


def test_update_favorite_duplicate_name(favorites_manager):
    """Test that updating to a duplicate name fails."""
    favorites_manager.add_favorite("name1", "cmd1")
    fav2 = favorites_manager.add_favorite("name2", "cmd2")

    result = favorites_manager.update_favorite(fav2.favorite_id, name="name1")
    assert result is None  # Should fail due to duplicate name


def test_update_favorite_not_found(favorites_manager):
    """Test updating a non-existent favorite returns None."""
    result = favorites_manager.update_favorite("nonexistent-id", name="new")
    assert result is None


def test_increment_usage(favorites_manager):
    """Test incrementing usage count."""
    favorite = favorites_manager.add_favorite("test", "cmd")

    assert favorite.use_count == 0
    assert favorite.last_used_at is None

    result = favorites_manager.increment_usage(favorite.favorite_id)
    assert result is True

    # Retrieve and verify
    updated = favorites_manager.get_favorite(favorite.favorite_id)
    assert updated.use_count == 1
    assert updated.last_used_at is not None

    # Increment again
    favorites_manager.increment_usage(favorite.favorite_id)
    updated = favorites_manager.get_favorite(favorite.favorite_id)
    assert updated.use_count == 2


def test_increment_usage_not_found(favorites_manager):
    """Test incrementing usage for non-existent favorite returns False."""
    result = favorites_manager.increment_usage("nonexistent-id")
    assert result is False


def test_search_favorites_by_name(favorites_manager):
    """Test searching favorites by name."""
    favorites_manager.add_favorite("test_script", "python test.py")
    favorites_manager.add_favorite("demo_script", "bash demo.sh")
    favorites_manager.add_favorite("production_deploy", "deploy.sh")

    results = favorites_manager.search_favorites("test")
    assert len(results) == 1
    assert results[0].name == "test_script"

    results = favorites_manager.search_favorites("script")
    assert len(results) == 2


def test_search_favorites_by_command(favorites_manager):
    """Test searching favorites by command content."""
    favorites_manager.add_favorite("py1", "python script.py --verbose")
    favorites_manager.add_favorite("py2", "python another.py")
    favorites_manager.add_favorite("bash1", "bash script.sh")

    results = favorites_manager.search_favorites("python")
    assert len(results) == 2

    results = favorites_manager.search_favorites("--verbose")
    assert len(results) == 1
    assert results[0].name == "py1"


def test_search_favorites_case_insensitive(favorites_manager):
    """Test that search is case-insensitive."""
    favorites_manager.add_favorite("TestScript", "PYTHON TEST.PY")

    results = favorites_manager.search_favorites("testscript")
    assert len(results) == 1

    results = favorites_manager.search_favorites("python")
    assert len(results) == 1


def test_search_favorites_no_match(favorites_manager):
    """Test searching with no matches returns empty list."""
    favorites_manager.add_favorite("test", "cmd")

    results = favorites_manager.search_favorites("nonexistent")
    assert results == []
