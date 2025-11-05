"""Integration tests for the favorites dashboard feature."""

import os

import pytest

from desto.app.favorites_ui import FavoritesTab
from desto.app.ui import UserInterfaceManager
from desto.redis.client import DestoRedisClient
from desto.redis.desto_manager import DestoManager

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
    # Cleanup
    if client.redis:
        client.redis.flushdb()


@pytest.fixture
def desto_manager(redis_client):
    """Create a DestoManager instance."""
    return DestoManager(redis_client)


def test_favorites_tab_initialization(desto_manager):
    """Test that FavoritesTab can be initialized with a desto_manager."""

    # Create a mock UI manager
    class MockUIManager:
        def __init__(self):
            self.tmux_manager = None
            self.favorites_tab = None

    ui_manager = MockUIManager()
    favorites_tab = FavoritesTab(ui_manager, desto_manager)

    assert favorites_tab is not None
    assert favorites_tab.ui_manager == ui_manager
    assert favorites_tab.desto_manager == desto_manager
    assert favorites_tab.desto_manager.favorites_manager is not None


def test_favorites_manager_accessible_from_desto_manager(desto_manager):
    """Test that favorites_manager is accessible from desto_manager."""
    assert hasattr(desto_manager, "favorites_manager")
    assert desto_manager.favorites_manager is not None

    # Test adding a favorite through the manager
    favorite = desto_manager.favorites_manager.add_favorite("test_cmd", "echo hello")
    assert favorite is not None
    assert favorite.name == "test_cmd"

    # Test retrieving it
    retrieved = desto_manager.favorites_manager.get_favorite_by_name("test_cmd")
    assert retrieved is not None
    assert retrieved.favorite_id == favorite.favorite_id


def test_user_interface_manager_with_desto_manager(desto_manager):
    """Test that UserInterfaceManager properly initializes with desto_manager."""

    # Create a mock UI and tmux manager
    class MockTmuxManager:
        def __init__(self):
            self.SCRIPTS_DIR = None

    class MockUI:
        def column(self):
            return self

        def style(self, *args):
            return self

    mock_ui = MockUI()
    mock_tmux = MockTmuxManager()
    mock_settings = {}

    # Create UI manager with desto_manager
    ui_manager = UserInterfaceManager(mock_ui, mock_settings, mock_tmux, desto_manager=desto_manager)

    assert ui_manager.desto_manager == desto_manager
    assert ui_manager.favorites_tab is not None
    assert ui_manager.favorites_tab.desto_manager == desto_manager


def test_favorites_workflow_integration(desto_manager):
    """Test a complete workflow: add, list, search, update, delete."""
    # Add multiple favorites
    fav1 = desto_manager.favorites_manager.add_favorite("deploy", "bash deploy.sh")
    fav2 = desto_manager.favorites_manager.add_favorite("test", "python -m pytest")
    fav3 = desto_manager.favorites_manager.add_favorite("debug", "python -m pdb")

    assert fav1 is not None
    assert fav2 is not None
    assert fav3 is not None

    # List all
    all_favs = desto_manager.favorites_manager.list_favorites()
    assert len(all_favs) == 3

    # Search
    search_results = desto_manager.favorites_manager.search_favorites("python")
    assert len(search_results) == 2

    # Update
    updated = desto_manager.favorites_manager.update_favorite(fav1.favorite_id, name="deploy_prod")
    assert updated is not None
    assert updated.name == "deploy_prod"

    # Increment usage
    desto_manager.favorites_manager.increment_usage(fav2.favorite_id)
    desto_manager.favorites_manager.increment_usage(fav2.favorite_id)
    updated_fav2 = desto_manager.favorites_manager.get_favorite(fav2.favorite_id)
    assert updated_fav2.use_count == 2

    # List sorted by use count
    sorted_favs = desto_manager.favorites_manager.list_favorites(sort_by="use_count")
    assert sorted_favs[0].favorite_id == fav2.favorite_id  # Most used first

    # Delete
    result = desto_manager.favorites_manager.delete_favorite(fav3.favorite_id)
    assert result is True

    # Verify deletion
    remaining = desto_manager.favorites_manager.list_favorites()
    assert len(remaining) == 2
