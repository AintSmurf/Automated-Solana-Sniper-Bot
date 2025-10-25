import sys, os
import psycopg2
from psycopg2 import sql
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from helpers.logging_manager import LoggingHandler
from helpers.credentials_utility import CredentialsUtility

logger = LoggingHandler.get_logger()
creds = CredentialsUtility()
db_creds = creds.get_db_creds()

def create_database():
    try:
        conn = psycopg2.connect(
            host=db_creds["DB_HOST"],
            port=db_creds["DB_PORT"],
            user=db_creds["DB_USER"],
            password=db_creds["DB_PASSWORD"],
            dbname="postgres"
        )
        conn.autocommit = True
        cur = conn.cursor()

        db_name = db_creds["DB_NAME"]
        user_name = db_creds["DB_USER"]

        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        exists = cur.fetchone()
        if not exists:
            cur.execute(sql.SQL("CREATE DATABASE {} OWNER {};")
                        .format(sql.Identifier(db_name), sql.Identifier(user_name)))
            logger.info(f"✅ Database '{db_name}' created successfully.")
        else:
            logger.info(f"ℹ️ Database '{db_name}' already exists.")

        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Failed to create database: {e}", exc_info=True)

def create_tables():
    try:
        conn_params = {
            "host": db_creds["DB_HOST"],
            "port": db_creds["DB_PORT"],
            "user": db_creds["DB_USER"],
            "password": db_creds["DB_PASSWORD"],
            "dbname": db_creds["DB_NAME"]
        }
        with psycopg2.connect(**conn_params) as conn:
            with conn.cursor() as cur:
                # TOKENS
                cur.execute("""
                CREATE TABLE IF NOT EXISTS tokens (
                    id SERIAL PRIMARY KEY,
                    token_address TEXT UNIQUE NOT NULL,
                    signature TEXT,
                    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # TOKEN STATS
                cur.execute("""
                CREATE TABLE IF NOT EXISTS token_stats (
                    id SERIAL PRIMARY KEY,
                    token_id INT REFERENCES tokens(id) ON DELETE CASCADE,
                    market_cap DOUBLE PRECISION,
                    liquidity_usd DOUBLE PRECISION,
                    dex_source TEXT,
                    holders_count INT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # SAFETY RESULTS
                cur.execute("""
                CREATE TABLE IF NOT EXISTS safety_results (
                    id SERIAL PRIMARY KEY,
                    token_id INT REFERENCES tokens(id) ON DELETE CASCADE,
                    lp_check BOOLEAN,
                    holders_check BOOLEAN,
                    volume_check BOOLEAN,
                    marketcap_check BOOLEAN,
                    rugcheck_score INT,
                    final_passed BOOLEAN,
                    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # TRADES
                cur.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id SERIAL PRIMARY KEY,
                    token_id INT REFERENCES tokens(id) ON DELETE CASCADE,
                    trade_type TEXT,
                    entry_usd DOUBLE PRECISION,
                    exit_usd DOUBLE PRECISION,
                    pnl_percent DOUBLE PRECISION,
                    trigger_reason TEXT,
                    simulation BOOLEAN,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # LIQUIDITY SNAPSHOTS
                cur.execute("""
                CREATE TABLE IF NOT EXISTS liquidity_snapshots (
                    id SERIAL PRIMARY KEY,
                    token_id INT REFERENCES tokens(id) ON DELETE CASCADE,
                    sol_liq DOUBLE PRECISION,
                    usdc_liq DOUBLE PRECISION,
                    usdt_liq DOUBLE PRECISION,
                    usd1_liq DOUBLE PRECISION,
                    total_liq DOUBLE PRECISION,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # TOKEN POOLS
                cur.execute("""
                CREATE TABLE IF NOT EXISTS token_pools (
                    id SERIAL PRIMARY KEY,
                    token_id INT REFERENCES tokens(id) ON DELETE CASCADE,
                    pool_address TEXT UNIQUE,
                    dex_source TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # SIGNATURES
                cur.execute("""
                CREATE TABLE IF NOT EXISTS signatures (
                    id SERIAL PRIMARY KEY,
                    token_id INT REFERENCES tokens(id) ON DELETE CASCADE,
                    buy_signature TEXT UNIQUE,
                    sell_signature TEXT,
                    buy_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    sell_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)

                conn.commit()
                logger.info("✅ Full relational schema created successfully.")
    except Exception as e:
        logger.error(f"❌ Failed to create tables: {e}", exc_info=True)

if __name__ == "__main__":
    create_database()
    create_tables()
