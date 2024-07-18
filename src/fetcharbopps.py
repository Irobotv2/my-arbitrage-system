import asyncio
import aiomysql
import logging
from datetime import datetime

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'arbitrage_user',
    'password': 'Newpassword1!',
    'db': 'arbitrage_system',
    'maxsize': 5,
    'minsize': 1,
}

# Configure logging
logging.basicConfig(filename='arbitrage_opportunities.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

async def fetch_all_opportunities(conn):
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute("""
            SELECT * FROM arbitrage_opportunities
        """)
        results = await cur.fetchall()
        return results

async def list_arbitrage_opportunities():
    pool = await aiomysql.create_pool(**DB_CONFIG)
    async with pool.acquire() as conn:
        opportunities = await fetch_all_opportunities(conn)
        for opp in opportunities:
            print(f"ID: {opp['id']}")
            print(f"Pair: {opp['pair']}")
            print(f"V2 Pair: {opp['v2_pair']}")
            print(f"V3 Pool: {opp['v3_pool']}")
            print(f"V2 Price: {opp['v2_price']}")
            print(f"V3 Price: {opp['v3_price']}")
            print(f"Basis Points: {opp['basis_points']}")
            print(f"Direction: {opp['direction']}")
            print(f"Timestamp: {opp['timestamp']}")
            print(f"Executed: {opp['executed']}")
            print(f"Execution Timestamp: {opp['execution_timestamp']}")
            print("------")

if __name__ == "__main__":
    asyncio.run(list_arbitrage_opportunities())
