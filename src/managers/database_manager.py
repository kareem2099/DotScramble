"""
Enhanced Database Manager for DotScramble
Handles user preferences and settings persistence using SQLite

Features:
- Theme persistence
- Effect settings memory
- Window state restoration
- Recent files tracking
- Application preferences
- Automatic backup
- Migration support
"""

import sqlite3
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Dict, List, Tuple
from contextlib import contextmanager
import threading

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from src.config import DIRS
except ImportError:
    # Fallback if config not available
    DIRS = {'backups': Path.home() / '.advanced_privacy_studio' / 'backups'}


class DatabaseManager:
    """
    Enhanced SQLite-based database manager for user preferences and settings.
    
    Features:
    - Single file database (user_settings.db)
    - Automatic initialization and migration
    - Thread-safe operations with connection pooling
    - In-memory caching for performance
    - Graceful fallback on errors
    - Privacy-focused (local storage only)
    - Automatic cleanup of old data
    """
    
    # Class-level lock for thread safety
    _lock = threading.RLock()
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the database manager.
        
        Args:
            db_path: Custom database path. If None, uses default location.
        """
        # Use custom path or default location
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = DIRS['backups'] / 'user_settings.db'
        
        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Cache for frequently accessed settings
        self._cache: Dict[str, Any] = {}
        self._cache_dirty = False
        
        # Initialize database
        self._init_database()
        
        # Load all settings into cache on startup
        self._load_cache()
        
        print(f"✅ Database initialized at: {self.db_path}")
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections with thread safety."""
        with self._lock:
            conn = sqlite3.connect(self.db_path, timeout=10.0)
            conn.row_factory = sqlite3.Row  # Enable column access by name
            try:
                yield conn
            finally:
                conn.close()
    
    def _init_database(self) -> None:
        """Initialize database schema with migration support."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Create main settings table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_preferences (
                        setting_key TEXT PRIMARY KEY,
                        setting_value TEXT NOT NULL,
                        setting_type TEXT DEFAULT 'general',
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Create index for faster lookups
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_settings_key 
                    ON user_preferences(setting_key)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_settings_type 
                    ON user_preferences(setting_type)
                ''')
                
                # Create migration tracking table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        description TEXT,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Create recent files table (optimized structure)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS recent_files (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_path TEXT NOT NULL UNIQUE,
                        file_name TEXT NOT NULL,
                        accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        file_size INTEGER,
                        file_type TEXT
                    )
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_recent_accessed 
                    ON recent_files(accessed_at DESC)
                ''')
                
                # Create application statistics table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS app_statistics (
                        stat_key TEXT PRIMARY KEY,
                        stat_value INTEGER DEFAULT 0,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Apply migrations if needed
                self._apply_migrations(cursor)
                
                conn.commit()
                print("✅ Database schema initialized successfully")
                
        except sqlite3.Error as e:
            print(f"❌ Database initialization error: {e}")
            # Don't raise - allow app to continue without database
    
    def _apply_migrations(self, cursor) -> None:
        """Apply database schema migrations."""
        try:
            # Get current migration version
            cursor.execute('SELECT MAX(version) FROM schema_migrations')
            result = cursor.fetchone()
            current_version = result[0] if result and result[0] else 0
            
            migrations = [
                (1, "Initial schema", None),
                (2, "Add setting_type and created_at columns", self._migrate_v2),
                (3, "Add recent_files table", None),  # Already in _init_database
                (4, "Add app_statistics table", None),  # Already in _init_database
            ]
            
            for version, description, migration_func in migrations:
                if current_version < version:
                    if migration_func:
                        migration_func(cursor)
                    cursor.execute(
                        'INSERT INTO schema_migrations (version, description) VALUES (?, ?)',
                        (version, description)
                    )
                    print(f"✅ Applied migration v{version}: {description}")
            
            print(f"✅ Database at version: {max(m[0] for m in migrations)}")
            
        except sqlite3.Error as e:
            print(f"⚠️ Migration error (non-critical): {e}")
    
    def _migrate_v2(self, cursor) -> None:
        """Migration v2: Add setting_type and created_at columns."""
        try:
            # Check if columns exist
            cursor.execute("PRAGMA table_info(user_preferences)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'setting_type' not in columns:
                cursor.execute('''
                    ALTER TABLE user_preferences 
                    ADD COLUMN setting_type TEXT DEFAULT 'general'
                ''')
            
            if 'created_at' not in columns:
                cursor.execute('''
                    ALTER TABLE user_preferences 
                    ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ''')
                
        except sqlite3.Error as e:
            print(f"⚠️ Migration v2 warning: {e}")
    
    def _load_cache(self) -> None:
        """Load all settings into memory cache for faster access."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT setting_key, setting_value FROM user_preferences')
                
                for row in cursor.fetchall():
                    try:
                        self._cache[row['setting_key']] = json.loads(row['setting_value'])
                    except json.JSONDecodeError:
                        print(f"⚠️ Invalid JSON for setting: {row['setting_key']}")
                
                print(f"✅ Loaded {len(self._cache)} settings into cache")
                
        except sqlite3.Error as e:
            print(f"⚠️ Cache loading error: {e}")
    
    def save_setting(self, key: str, value: Any, setting_type: str = 'general') -> bool:
        """
        Save a user setting to the database.
        
        Args:
            key: Setting identifier (e.g., 'last_theme', 'blur_strength')
            value: Setting value (will be JSON serialized)
            setting_type: Category of setting (theme, effect, window, etc.)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # JSON serialize the value
            json_value = json.dumps(value, ensure_ascii=False)
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO user_preferences 
                    (setting_key, setting_value, setting_type, updated_at) 
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ''', (key, json_value, setting_type))
                
                conn.commit()
                
                # Update cache
                self._cache[key] = value
                
                return True
                
        except (sqlite3.Error, json.JSONDecodeError) as e:
            print(f"❌ Failed to save setting {key}: {e}")
            return False
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        Retrieve a user setting from the database.
        
        Args:
            key: Setting identifier
            default: Default value if setting not found
            
        Returns:
            The setting value or default if not found
        """
        # Check cache first (fast path)
        if key in self._cache:
            return self._cache[key]
        
        # Not in cache, try database
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT setting_value FROM user_preferences 
                    WHERE setting_key = ?
                ''', (key,))
                
                result = cursor.fetchone()
                
                if result:
                    value = json.loads(result['setting_value'])
                    self._cache[key] = value
                    return value
                else:
                    # Cache the default value
                    self._cache[key] = default
                    return default
                    
        except (sqlite3.Error, json.JSONDecodeError) as e:
            print(f"❌ Failed to retrieve setting {key}: {e}")
            return default
    
    def delete_setting(self, key: str) -> bool:
        """
        Delete a user setting from the database.
        
        Args:
            key: Setting identifier to delete
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM user_preferences WHERE setting_key = ?', (key,))
                
                if cursor.rowcount > 0:
                    # Remove from cache
                    self._cache.pop(key, None)
                    
                    conn.commit()
                    print(f"🗑️ Setting deleted: {key}")
                    return True
                else:
                    print(f"⚠️ Setting not found: {key}")
                    return False
                    
        except sqlite3.Error as e:
            print(f"❌ Failed to delete setting {key}: {e}")
            return False
    
    def get_all_settings(self, setting_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieve all user settings or settings of a specific type.
        
        Args:
            setting_type: Optional filter by setting type
        
        Returns:
            Dictionary of all settings
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                if setting_type:
                    cursor.execute('''
                        SELECT setting_key, setting_value 
                        FROM user_preferences 
                        WHERE setting_type = ?
                    ''', (setting_type,))
                else:
                    cursor.execute('SELECT setting_key, setting_value FROM user_preferences')
                
                settings = {}
                for row in cursor.fetchall():
                    try:
                        settings[row['setting_key']] = json.loads(row['setting_value'])
                    except json.JSONDecodeError:
                        print(f"⚠️ Invalid JSON for setting: {row['setting_key']}")
                
                return settings
                
        except sqlite3.Error as e:
            print(f"❌ Failed to retrieve all settings: {e}")
            return {}
    
    def bulk_save_settings(self, settings_dict: Dict[str, Any], setting_type: str = 'general') -> bool:
        """
        Save multiple settings in a single transaction.
        
        Args:
            settings_dict: Dictionary of key-value pairs to save
            setting_type: Category for all settings
            
        Returns:
            bool: True if all settings saved successfully
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Prepare batch insert/update
                values = []
                for key, value in settings_dict.items():
                    json_value = json.dumps(value, ensure_ascii=False)
                    values.append((key, json_value, setting_type))
                
                # Use executemany for better performance
                cursor.executemany('''
                    INSERT OR REPLACE INTO user_preferences 
                    (setting_key, setting_value, setting_type, updated_at) 
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ''', values)
                
                conn.commit()
                
                # Update cache
                self._cache.update(settings_dict)
                
                print(f"💾 Bulk save completed: {len(settings_dict)} settings")
                return True
                
        except (sqlite3.Error, json.JSONDecodeError) as e:
            print(f"❌ Bulk save failed: {e}")
            return False
    
    def clear_all_settings(self, setting_type: Optional[str] = None) -> bool:
        """
        Clear all user settings or settings of a specific type.
        
        Args:
            setting_type: Optional - clear only this type. If None, clear all.
            
        Returns:
            bool: True if successful
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                if setting_type:
                    cursor.execute('DELETE FROM user_preferences WHERE setting_type = ?', 
                                 (setting_type,))
                    # Remove from cache
                    keys_to_remove = [k for k, v in self.get_all_settings(setting_type).items()]
                    for key in keys_to_remove:
                        self._cache.pop(key, None)
                else:
                    cursor.execute('DELETE FROM user_preferences')
                    self._cache.clear()
                
                conn.commit()
                print(f"🗑️ Settings cleared{f' (type: {setting_type})' if setting_type else ''}")
                return True
                
        except sqlite3.Error as e:
            print(f"❌ Failed to clear settings: {e}")
            return False
    
    # ==================== Theme Management ====================
    
    def get_last_used_theme(self) -> str:
        """Get the last used theme, with fallback to default."""
        return self.get_setting('last_theme', 'midnight')
    
    def save_last_used_theme(self, theme_key: str) -> bool:
        """Save the currently used theme."""
        return self.save_setting('last_theme', theme_key, 'theme')
    
    # ==================== Effect Settings ====================
    
    def get_last_effect_settings(self) -> Dict[str, Any]:
        """Get last used effect settings with defaults."""
        defaults = {
            'effect_type': 'blur',
            'detection_mode': 'face',
            'blur_strength': 51,
            'pixel_size': 15,
            'opacity': 100,
            'edge_blur': 5
        }
        
        saved = self.get_setting('last_effect_settings', {})
        if isinstance(saved, dict):
            # Merge with defaults (defaults for missing keys)
            for key, default_value in defaults.items():
                if key not in saved:
                    saved[key] = default_value
            return saved
        else:
            return defaults
    
    def save_last_effect_settings(self, settings: Dict[str, Any]) -> bool:
        """Save the current effect settings."""
        return self.save_setting('last_effect_settings', settings, 'effect')
    
    # ==================== Window State ====================
    
    def get_window_state(self) -> Dict[str, Any]:
        """Get saved window state with defaults."""
        defaults = {
            'width': 1400,
            'height': 900,
            'x': 100,
            'y': 100,
            'maximized': False
        }
        
        saved = self.get_setting('window_state', {})
        if isinstance(saved, dict):
            for key, default_value in defaults.items():
                if key not in saved:
                    saved[key] = default_value
            return saved
        else:
            return defaults
    
    def save_window_state(self, width: int, height: int, x: int, y: int, 
                         maximized: bool = False) -> bool:
        """Save current window position and size."""
        state = {
            'width': width,
            'height': height,
            'x': x,
            'y': y,
            'maximized': maximized
        }
        return self.save_setting('window_state', state, 'window')
    
    # ==================== Recent Files Management ====================
    
    def add_recent_file(self, file_path: str) -> bool:
        """
        Add a file to the recent files table.
        
        Args:
            file_path: Full path to the file
            
        Returns:
            bool: True if successful
        """
        try:
            file_path_obj = Path(file_path)
            
            # Get file info
            file_name = file_path_obj.name
            file_size = file_path_obj.stat().st_size if file_path_obj.exists() else 0
            file_type = file_path_obj.suffix.lower()
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Delete if already exists (to update timestamp)
                cursor.execute('DELETE FROM recent_files WHERE file_path = ?', (file_path,))
                
                # Insert new record
                cursor.execute('''
                    INSERT INTO recent_files 
                    (file_path, file_name, file_size, file_type, accessed_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (file_path, file_name, file_size, file_type))
                
                # Keep only last 20 files
                cursor.execute('''
                    DELETE FROM recent_files 
                    WHERE id NOT IN (
                        SELECT id FROM recent_files 
                        ORDER BY accessed_at DESC 
                        LIMIT 20
                    )
                ''')
                
                conn.commit()
                return True
                
        except (sqlite3.Error, OSError) as e:
            print(f"❌ Failed to add recent file: {e}")
            return False
    
    def get_recent_files(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get list of recent files with metadata.
        
        Args:
            limit: Maximum number of files to return
            
        Returns:
            List of file dictionaries with path, name, size, type, and access time
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT file_path, file_name, file_size, file_type, accessed_at
                    FROM recent_files
                    ORDER BY accessed_at DESC
                    LIMIT ?
                ''', (limit,))
                
                files = []
                for row in cursor.fetchall():
                    files.append({
                        'path': row['file_path'],
                        'name': row['file_name'],
                        'size': row['file_size'],
                        'type': row['file_type'],
                        'accessed_at': row['accessed_at']
                    })
                
                return files
                
        except sqlite3.Error as e:
            print(f"❌ Failed to get recent files: {e}")
            return []
    
    def clear_recent_files(self) -> bool:
        """Clear all recent files."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM recent_files')
                conn.commit()
                print("🗑️ Recent files cleared")
                return True
                
        except sqlite3.Error as e:
            print(f"❌ Failed to clear recent files: {e}")
            return False
    
    # ==================== Application Statistics ====================
    
    def increment_stat(self, stat_key: str, amount: int = 1) -> bool:
        """
        Increment a statistic counter.
        
        Args:
            stat_key: Statistic identifier (e.g., 'images_processed', 'app_launches')
            amount: Amount to increment by (default 1)
            
        Returns:
            bool: True if successful
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO app_statistics (stat_key, stat_value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(stat_key) DO UPDATE SET
                        stat_value = stat_value + ?,
                        updated_at = CURRENT_TIMESTAMP
                ''', (stat_key, amount, amount))
                
                conn.commit()
                return True
                
        except sqlite3.Error as e:
            print(f"❌ Failed to increment stat {stat_key}: {e}")
            return False
    
    def get_stat(self, stat_key: str, default: int = 0) -> int:
        """Get a statistic value."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT stat_value FROM app_statistics WHERE stat_key = ?', 
                             (stat_key,))
                
                result = cursor.fetchone()
                return result['stat_value'] if result else default
                
        except sqlite3.Error as e:
            print(f"❌ Failed to get stat {stat_key}: {e}")
            return default
    
    def get_all_stats(self) -> Dict[str, int]:
        """Get all statistics."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT stat_key, stat_value FROM app_statistics')
                
                return {row['stat_key']: row['stat_value'] for row in cursor.fetchall()}
                
        except sqlite3.Error as e:
            print(f"❌ Failed to get all stats: {e}")
            return {}
    
    # ==================== Application Preferences ====================
    
    def get_real_time_preview_enabled(self) -> bool:
        """Get real-time preview preference."""
        return self.get_setting('real_time_preview_enabled', False)
    
    def save_real_time_preview_enabled(self, enabled: bool) -> bool:
        """Save real-time preview preference."""
        return self.save_setting('real_time_preview_enabled', enabled, 'preference')
    
    def get_auto_save_enabled(self) -> bool:
        """Get auto-save preference."""
        return self.get_setting('auto_save_enabled', False)
    
    def save_auto_save_enabled(self, enabled: bool) -> bool:
        """Save auto-save preference."""
        return self.save_setting('auto_save_enabled', enabled, 'preference')
    
    # ==================== Language Settings ====================
    
    def get_last_used_language(self) -> str:
        """Get the last used language, with fallback to default (English)."""
        return self.get_setting('last_language', 'en')
    
    def save_last_used_language(self, language_code: str) -> bool:
        """Save the currently used language."""
        return self.save_setting('last_language', language_code, 'language')
    
    # ==================== Database Maintenance ====================
    
    def get_database_info(self) -> Dict[str, Any]:
        """Get information about the database."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Count settings
                cursor.execute('SELECT COUNT(*) as count FROM user_preferences')
                setting_count = cursor.fetchone()['count']
                
                # Count recent files
                cursor.execute('SELECT COUNT(*) as count FROM recent_files')
                file_count = cursor.fetchone()['count']
                
                # Get last update time
                cursor.execute('SELECT MAX(updated_at) as last_update FROM user_preferences')
                last_update = cursor.fetchone()['last_update']
                
                # Get database file size
                file_size = self.db_path.stat().st_size if self.db_path.exists() else 0
                
                # Get migration version
                cursor.execute('SELECT MAX(version) as version FROM schema_migrations')
                db_version = cursor.fetchone()['version'] or 0
                
                return {
                    'file_path': str(self.db_path),
                    'setting_count': setting_count,
                    'recent_files_count': file_count,
                    'last_update': last_update,
                    'file_size_bytes': file_size,
                    'file_size_kb': round(file_size / 1024, 2) if file_size > 0 else 0,
                    'database_version': db_version,
                    'cache_size': len(self._cache)
                }
                
        except sqlite3.Error as e:
            print(f"❌ Failed to get database info: {e}")
            return {}
    
    def vacuum_database(self) -> bool:
        """Optimize database by running VACUUM (reclaim space)."""
        try:
            with self._get_connection() as conn:
                conn.execute('VACUUM')
                print("✅ Database optimized")
                return True
                
        except sqlite3.Error as e:
            print(f"❌ Database vacuum failed: {e}")
            return False
    
    def backup_database(self, backup_path: Optional[str] = None) -> bool:
        """
        Create a backup of the database file.
        
        Args:
            backup_path: Custom backup path. If None, uses timestamped name.
            
        Returns:
            bool: True if backup successful
        """
        try:
            if not backup_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = self.db_path.parent / f"user_settings_backup_{timestamp}.db"
            
            import shutil
            shutil.copy2(self.db_path, backup_path)
            print(f"💾 Database backup created: {backup_path}")
            return True
            
        except Exception as e:
            print(f"❌ Database backup failed: {e}")
            return False
    
    def export_settings_json(self, export_path: str) -> bool:
        """
        Export all settings to a JSON file for backup or transfer.
        
        Args:
            export_path: Path to save JSON file
            
        Returns:
            bool: True if successful
        """
        try:
            all_settings = self.get_all_settings()
            
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(all_settings, f, indent=2, ensure_ascii=False)
            
            print(f"💾 Settings exported to: {export_path}")
            return True
            
        except Exception as e:
            print(f"❌ Settings export failed: {e}")
            return False
    
    def import_settings_json(self, import_path: str) -> bool:
        """
        Import settings from a JSON file.
        
        Args:
            import_path: Path to JSON file
            
        Returns:
            bool: True if successful
        """
        try:
            with open(import_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            
            if not isinstance(settings, dict):
                print("❌ Invalid settings format")
                return False
            
            return self.bulk_save_settings(settings)
            
        except Exception as e:
            print(f"❌ Settings import failed: {e}")
            return False
    
    def close(self) -> None:
        """Close database connections and clean up."""
        # SQLite connections are automatically closed when context manager exits
        # Clear cache to free memory
        self._cache.clear()
        print("✅ Database manager closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False  # Don't suppress exceptions


# ==================== Global Instance Management ====================

# Global instance for easy access throughout the application
_db_manager: Optional[DatabaseManager] = None


def init_database_manager(db_path: Optional[str] = None) -> DatabaseManager:
    """
    Initialize the global database manager instance.
    
    Args:
        db_path: Optional custom database path
        
    Returns:
        DatabaseManager instance
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager(db_path)
    return _db_manager


def get_db_manager() -> Optional[DatabaseManager]:
    """Get the global database manager instance."""
    return _db_manager


# ==================== Example Usage ====================

def example_usage():
    """Example of how to use the DatabaseManager."""
    print("=" * 60)
    print("DatabaseManager Example Usage")
    print("=" * 60)
    
    # Initialize database
    db = DatabaseManager()
    
    # Save some settings
    print("\n1. Saving settings...")
    db.save_setting('last_theme', 'midnight', 'theme')
    db.save_setting('blur_strength', 51, 'effect')
    db.save_setting('window_state', {'width': 1400, 'height': 900}, 'window')
    
    # Retrieve settings
    print("\n2. Retrieving settings...")
    theme = db.get_setting('last_theme', 'default_theme')
    print(f"   Theme: {theme}")
    strength = db.get_setting('blur_strength', 30)
    print(f"   Blur Strength: {strength}")
    
    # Bulk operations
    print("\n3. Bulk save...")
    settings = {
        'effect_type': 'blur',
        'detection_mode': 'face',
        'opacity': 100
    }
    db.bulk_save_settings(settings, 'effect')
    
    # Recent files
    print("\n4. Managing recent files...")
    db.add_recent_file('/path/to/image1.jpg')
    db.add_recent_file('/path/to/image2.png')
    recent = db.get_recent_files(5)
    print(f"   Recent files: {len(recent)}")
    
    # Statistics
    print("\n5. Statistics...")
    db.increment_stat('images_processed')
    db.increment_stat('images_processed')
    db.increment_stat('app_launches')
    stats = db.get_all_stats()
    print(f"   Stats: {stats}")
    
    # Get all settings
    print("\n6. All settings...")
    all_settings = db.get_all_settings()
    print(f"   Total settings: {len(all_settings)}")
    
    # Database info
    print("\n7. Database info...")
    info = db.get_database_info()
    for key, value in info.items():
        print(f"   {key}: {value}")
    
    print("\n" + "=" * 60)
    print("✅ Example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    example_usage()