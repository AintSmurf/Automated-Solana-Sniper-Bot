import sys, os
import psycopg2
from psycopg2 import sql
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from helpers.logging_manager import LoggingHandler
from helpers.credentials_utility import CredentialsUtility
import time

MAX_RETRIES = 10
RETRY_DELAY = 3

logger = LoggingHandler.get_logger()
creds = CredentialsUtility()
db_creds = creds.get_db_creds()

def create_database():
    for attempt in range(1, MAX_RETRIES + 1):
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
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                raise

def create_tables():
    
    for attempt in range(1, MAX_RETRIES + 1):
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
                    # TOKEN VOLUME
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS token_volumes (
                            id SERIAL PRIMARY KEY,
                            token_id INT REFERENCES tokens(id) ON DELETE CASCADE,
                            buy_usd DOUBLE PRECISION DEFAULT 0,
                            sell_usd DOUBLE PRECISION DEFAULT 0,
                            total_usd DOUBLE PRECISION DEFAULT 0,
                            buy_count INT DEFAULT 0,
                            sell_count INT DEFAULT 0,
                            buy_ratio DOUBLE PRECISION DEFAULT 0,
                            net_flow DOUBLE PRECISION DEFAULT 0,
                            launch_time TIMESTAMP,
                            launch_volume DOUBLE PRECISION DEFAULT 0,
                            delta_volume DOUBLE PRECISION DEFAULT 0,
                            snapshot_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)


                    # TOKEN STATS
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS token_stats (
                            id SERIAL PRIMARY KEY,
                            token_id INT REFERENCES tokens(id) ON DELETE CASCADE,
                            market_cap DOUBLE PRECISION,
                            holders_count INT
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
                        score INT,
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
                            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            status TEXT,
                            confirmed_at TIMESTAMP,
                            finalized_at TIMESTAMP
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
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                raise

if __name__ == "__main__":
    create_database()
    create_tables()
