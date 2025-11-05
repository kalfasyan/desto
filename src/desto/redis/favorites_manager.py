"""Favorites manager for storing and retrieving user's favorite commands."""

from datetime import datetime
from typing import List, Optional

from loguru import logger

from .client import DestoRedisClient
from .models import FavoriteCommand


class FavoriteCommandsManager:
    """Manages user's favorite commands."""

    def __init__(self, redis_client: DestoRedisClient):
        self.redis = redis_client

    def add_favorite(self, name: str, command: str) -> Optional[FavoriteCommand]:
        """Add a new favorite command.

        Args:
            name: User-friendly name for the favorite
            command: The actual command string

        Returns:
            FavoriteCommand object if successful, None otherwise
        """
        # Check if a favorite with this name already exists
        existing = self.get_favorite_by_name(name)
        if existing:
            logger.warning(f"Favorite with name '{name}' already exists")
            return None

        favorite = FavoriteCommand(name=name, command=command, created_at=datetime.now(), use_count=0)

        # Store in Redis
        favorite_key = f"desto:favorite:{favorite.favorite_id}"
        self.redis.redis.hset(favorite_key, mapping=favorite.to_dict())

        # Add to name index for quick lookups
        name_index_key = f"desto:favorite:name:{name}"
        self.redis.redis.set(name_index_key, favorite.favorite_id)

        # Add to favorites set
        self.redis.redis.sadd("desto:favorites:all", favorite.favorite_id)

        logger.info(f"Added favorite '{name}' with ID {favorite.favorite_id}")
        return favorite

    def list_favorites(self, sort_by: str = "created_at") -> List[FavoriteCommand]:
        """List all favorite commands.

        Args:
            sort_by: Field to sort by ('created_at', 'use_count', 'name')

        Returns:
            List of FavoriteCommand objects
        """
        favorite_ids = self.redis.redis.smembers("desto:favorites:all")
        if not favorite_ids:
            return []

        favorites = []
        for fav_id in favorite_ids:
            if isinstance(fav_id, bytes):
                fav_id = fav_id.decode("utf-8")

            favorite = self.get_favorite(fav_id)
            if favorite:
                favorites.append(favorite)

        # Sort favorites
        if sort_by == "use_count":
            favorites.sort(key=lambda f: f.use_count, reverse=True)
        elif sort_by == "name":
            favorites.sort(key=lambda f: f.name.lower())
        else:  # created_at
            favorites.sort(key=lambda f: f.created_at or datetime.min, reverse=True)

        return favorites

    def get_favorite(self, favorite_id: str) -> Optional[FavoriteCommand]:
        """Get a favorite by ID.

        Args:
            favorite_id: UUID of the favorite

        Returns:
            FavoriteCommand object if found, None otherwise
        """
        favorite_key = f"desto:favorite:{favorite_id}"
        data = self.redis.redis.hgetall(favorite_key)

        if not data:
            return None

        return FavoriteCommand.from_dict(data)

    def get_favorite_by_name(self, name: str) -> Optional[FavoriteCommand]:
        """Get a favorite by name.

        Args:
            name: Name of the favorite

        Returns:
            FavoriteCommand object if found, None otherwise
        """
        name_index_key = f"desto:favorite:name:{name}"
        favorite_id = self.redis.redis.get(name_index_key)

        if not favorite_id:
            return None

        if isinstance(favorite_id, bytes):
            favorite_id = favorite_id.decode("utf-8")

        return self.get_favorite(favorite_id)

    def delete_favorite(self, favorite_id: str) -> bool:
        """Delete a favorite command.

        Args:
            favorite_id: UUID of the favorite to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        # Get the favorite first to get its name
        favorite = self.get_favorite(favorite_id)
        if not favorite:
            logger.warning(f"Favorite {favorite_id} not found")
            return False

        # Delete from Redis
        favorite_key = f"desto:favorite:{favorite_id}"
        self.redis.redis.delete(favorite_key)

        # Delete from name index
        name_index_key = f"desto:favorite:name:{favorite.name}"
        self.redis.redis.delete(name_index_key)

        # Remove from favorites set
        self.redis.redis.srem("desto:favorites:all", favorite_id)

        logger.info(f"Deleted favorite '{favorite.name}' (ID: {favorite_id})")
        return True

    def update_favorite(self, favorite_id: str, name: Optional[str] = None, command: Optional[str] = None) -> Optional[FavoriteCommand]:
        """Update a favorite command's name or command.

        Args:
            favorite_id: UUID of the favorite to update
            name: New name (optional)
            command: New command (optional)

        Returns:
            Updated FavoriteCommand object if successful, None otherwise
        """
        favorite = self.get_favorite(favorite_id)
        if not favorite:
            logger.warning(f"Favorite {favorite_id} not found")
            return None

        old_name = favorite.name

        # Update fields if provided
        if name is not None and name != old_name:
            # Check if new name already exists
            existing = self.get_favorite_by_name(name)
            if existing and existing.favorite_id != favorite_id:
                logger.warning(f"Favorite with name '{name}' already exists")
                return None

            # Update name index
            old_name_index = f"desto:favorite:name:{old_name}"
            new_name_index = f"desto:favorite:name:{name}"
            self.redis.redis.delete(old_name_index)
            self.redis.redis.set(new_name_index, favorite_id)

            favorite.name = name

        if command is not None:
            favorite.command = command

        # Update in Redis
        favorite_key = f"desto:favorite:{favorite_id}"
        self.redis.redis.hset(favorite_key, mapping=favorite.to_dict())

        logger.info(f"Updated favorite {favorite_id}")
        return favorite

    def increment_usage(self, favorite_id: str) -> bool:
        """Increment the use count for a favorite.

        Args:
            favorite_id: UUID of the favorite

        Returns:
            True if successful, False otherwise
        """
        favorite = self.get_favorite(favorite_id)
        if not favorite:
            logger.warning(f"Favorite {favorite_id} not found")
            return False

        favorite.use_count += 1
        favorite.last_used_at = datetime.now()

        # Update in Redis
        favorite_key = f"desto:favorite:{favorite_id}"
        self.redis.redis.hset(favorite_key, mapping=favorite.to_dict())

        logger.info(f"Incremented usage for favorite '{favorite.name}' to {favorite.use_count}")
        return True

    def search_favorites(self, query: str) -> List[FavoriteCommand]:
        """Search favorites by name or command.

        Args:
            query: Search query string

        Returns:
            List of matching FavoriteCommand objects
        """
        all_favorites = self.list_favorites()
        query_lower = query.lower()

        matching = [fav for fav in all_favorites if query_lower in fav.name.lower() or query_lower in fav.command.lower()]

        return matching
