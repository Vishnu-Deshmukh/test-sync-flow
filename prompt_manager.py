import logging
from typing import Optional, Dict, Any, Union
from datetime import datetime
from pymongo import MongoClient
import Config

from data_extraction.utils.github_repo_prompts import Prompts

class PromptManager:
    _instance = None
    _cache = {}
    def __new__(cls, *args, **kwargs):
        """Singleton pattern to share prompt cache across workers in the same process."""
        if not cls._instance:
            cls._instance = super(PromptManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, db_client=None, cache_enabled: bool = True):
        if not hasattr(self, "initialized"):
            self.db = db_client if db_client else MongoClient(Config.MONGO_URL)[Config.MONGO_DB_NAME]
            self.collection = self.db.get_collection("prompt_templates")
            self.cache_enabled = cache_enabled
            self.initialized = True

    def get_prompt(self, prompt_name: str, **kwargs: Any) -> str:
        """Fetches string prompt from prompt_templates collection."""
        template = self._get_raw_item(prompt_name)

        if not template:
            static_prompt = getattr(Prompts, prompt_name, None)
            if static_prompt and isinstance(static_prompt, str):
                self._auto_seed(prompt_name, static_prompt, item_type="prompt")
                template = static_prompt
            else:
                logging.error(f"Prompt '{prompt_name}' not found.")
                return ""

        if kwargs and isinstance(template, str):
            try:
                return template.format(**kwargs)
            except KeyError:
                logging.exception(f"Missing variable when formatting prompt '{prompt_name}'.")
                return template

        return template if isinstance(template, str) else ""

    def get_schema(self, schema_name: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fetches dictionary JSON Schema from the SAME prompt_templates collection."""
        schema_dict = self._get_raw_item(schema_name)

        if not schema_dict:
            if default is not None and isinstance(default, dict):
                logging.info(f"Auto-seeding default schema for '{schema_name}' into prompt_templates...")
                self._auto_seed(schema_name, default, item_type="schema")
                schema_dict = default
            else:
                logging.error(f"Schema '{schema_name}' not found.")
                return {}

        return schema_dict if isinstance(schema_dict, dict) else {}

    def _get_raw_item(self, item_name: str) -> Optional[Union[str, Dict[str, Any]]]:
        if self.cache_enabled and item_name in self._cache:
            return self._cache[item_name]

        try:
            doc = self.collection.find_one({"name": item_name, "is_active": True})
            if doc and "template" in doc:
                item_value = doc["template"]
                self._cache[item_name] = item_value
                return item_value
        except Exception:
            logging.exception(f"MongoDB lookup failed for '{item_name}'.")

        return None

    def _auto_seed(self, name: str, value: Union[str, Dict[str, Any]], item_type: str) -> None:
        try:
            self.collection.update_one(
                {"name": name},
                {
                    "$setOnInsert": {
                        "name": name,
                        "type": item_type,
                        "template": value,
                        "version": 1,
                        "is_active": True,
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            self._cache[name] = value
            logging.info(f"Auto-seeded {item_type} '{name}' into prompt_templates collection.")
        except Exception:
            logging.exception(f"Failed to auto-seed '{name}'")

    def clear_cache(self):
        """Clears the in-memory cache (useful if you update prompts, schemas)."""
        self._cache.clear()
        logging.info("PromptManager cache cleared.")