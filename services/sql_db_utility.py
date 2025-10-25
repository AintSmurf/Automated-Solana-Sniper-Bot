import psycopg2
from psycopg2 import extras
from helpers.logging_manager import LoggingHandler
from services.bot_context import BotContext

Logger = LoggingHandler.get_logger()

class SqlDBUtility:
    def __init__(self, ctx: BotContext):
        self.creds = ctx.api_keys["db"]
        self.conn = None

    def close(self):
        """Manually close the DB connection (called during bot shutdown)."""
        if self.conn and not self.conn.closed:
            self.conn.close()
            Logger.info("🛑 DB connection closed.")

    def create_connection(self):
        """Create or reuse a persistent DB connection."""
        if self.conn is None or self.conn.closed:
            self.conn = psycopg2.connect(
                host=self.creds["DB_HOST"],
                port=self.creds["DB_PORT"],
                user=self.creds["DB_USER"],
                password=self.creds["DB_PASSWORD"],
                dbname=self.creds["DB_NAME"]
            )
            Logger.info("✅ Connected to SQL database.")
        return self.conn

    def execute_select(self, sql: str, params: tuple = None):
        conn = self.create_connection()
        try:
            Logger.debug(f"Executing SELECT: {sql}")
            with conn.cursor(cursor_factory=extras.DictCursor) as cur:
                cur.execute(sql, params or ())
                return cur.fetchall()
        except Exception as e:
            Logger.error(f"❌ Failed SELECT: {sql} — {e}", exc_info=True)
            raise

    def execute_insert(self, sql: str, params: tuple = None) -> int:
        conn = self.create_connection()
        inserted_id = None
        try:
            Logger.debug(f"Executing INSERT: {sql} with params={params}")
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                if cur.description: 
                    inserted_id = cur.fetchone()[0]
            conn.commit()
            Logger.info("✅ Insert successful.")
            return inserted_id
        except Exception as e:
            conn.rollback()
            Logger.error(f"❌ Failed INSERT: {e}", exc_info=True)
            raise

    def execute_update(self, sql: str, params: tuple = None) -> int:
        conn = self.create_connection()
        try:
            Logger.debug(f"Executing UPDATE: {sql} with params={params}")
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                affected = cur.rowcount
            conn.commit()
            Logger.info(f"✏️ Updated {affected} row(s).")
            return affected
        except Exception as e:
            conn.rollback()
            Logger.error(f"❌ Failed UPDATE: {e}", exc_info=True)
            raise

    def execute_delete(self, sql: str, params: tuple = None) -> int:
        conn = self.create_connection()
        try:
            Logger.debug(f"Executing DELETE: {sql} with params={params}")
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                affected = cur.rowcount
            conn.commit()
            Logger.info(f"🗑️ Deleted {affected} row(s).")
            return affected
        except Exception as e:
            conn.rollback()
            Logger.error(f"❌ Failed DELETE: {e}", exc_info=True)
            raise
