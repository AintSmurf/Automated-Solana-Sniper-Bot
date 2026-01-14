import json
import hashlib
from services.sql_db_utility import SqlDBUtility
from services.bot_context import BotContext


class ConfigVersionDAO:
    def __init__(self, ctx: BotContext):
        self.sql_helper: SqlDBUtility = ctx.get("sql_db")

    @staticmethod
    def _make_hash(settings: dict) -> str:
        normalized = json.dumps(
            settings,
            sort_keys=True,
            separators=(",", ":"), 
            ensure_ascii=False,
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def get_or_create_config(self, label: str, settings: dict) -> int:
        cfg_hash = self._make_hash(settings)
        rows = self.sql_helper.execute_select(
            "SELECT id FROM config_versions WHERE config_hash = %s",
            (cfg_hash,),
        )
        if rows:
            return rows[0]["id"]
        sql = """
        INSERT INTO config_versions (label, settings_json, config_hash)
        VALUES (%s, %s::jsonb, %s)
        RETURNING id;
        """
        settings_json = json.dumps(
            settings,
            sort_keys=True,
            ensure_ascii=False,
        )
        return self.sql_helper.execute_insert(sql, (label, settings_json, cfg_hash))
