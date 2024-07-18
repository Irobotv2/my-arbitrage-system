import asyncio
import aiohttp
import aiomysql
import logging
from decimal import Decimal, getcontext
from datetime import datetime, timedelta

# Set higher precision for Decimal calculations
getcontext().prec = 30

# Configure logging
logging.basicConfig(filename='/home/irobot/projects/my-arbitrage-system/src/uniswap_v2_pair_updater.log', 
                    level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'arbitrage_user',
    'password': 'Newpassword1!',
    'db': 'arbitrage_system',
    'maxsize': 5,
    'minsize': 1,
}

# API configuration
API_KEY = "bde86d5008a99eaf066b94e4cfcad7fc"
UNISWAP_V2_URL = f"https://gateway-arbitrum.network.thegraph.com/api/{API_KEY}/subgraphs/id/EYCKATKGBKLWvSfwvBjzfCBmGwYNdVkduYXVivCsLRFu"

# Rate limiting
RATE_LIMIT = asyncio.Semaphore(5)  # Adjust this value based on API limitations

async def fetch_v2_pair(session, token0, token1):
    query = """
    query($token0: String!, $token1: String!) {
      pairs(where: {token0_in: [$token0, $token1], token1_in: [$token0, $token1]}) {
        id
        token0 { id symbol }
        token1 { id symbol }
        reserve0
        reserve1
        reserveUSD
      }
    }
    """
    variables = {"token0": token0.lower(), "token1": token1.lower()}
    async with RATE_LIMIT:
        try:
            async with session.post(UNISWAP_V2_URL, json={'query': query, 'variables': variables}) as response:
                if response.status == 200:
                    data = await response.json()
                    logging.debug(f"Full response for {token0}-{token1}: {data}")
                    if 'data' in data and 'pairs' in data['data']:
                        if not data['data']['pairs']:
                            logging.info(f"No V2 pair found for tokens {token0} and {token1}")
                        return data['data']['pairs']
                    else:
                        logging.error(f"Unexpected response format: {data}")
                        return None
                else:
                    logging.error(f"Failed to fetch V2 pair: {await response.text()}")
                    return None
        except Exception as e:
            logging.error(f"Error fetching V2 pair for {token0}-{token1}: {str(e)}")
            return None

async def insert_or_update_v2_pair(cur, pair):
    try:
        reserve0 = Decimal(pair['reserve0'])
        reserve1 = Decimal(pair['reserve1'])
        
        # Calculate the price (reserve1 / reserve0)
        calculated_price = reserve1 / reserve0 if reserve0 != 0 else Decimal('0')
        
        await cur.execute("""
            INSERT INTO uniswap_v2_pairs 
            (pair_address, token0_address, token1_address, reserve0, reserve1, total_liquidity_usd, calculated_price) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            reserve0 = VALUES(reserve0),
            reserve1 = VALUES(reserve1),
            total_liquidity_usd = VALUES(total_liquidity_usd),
            calculated_price = VALUES(calculated_price)
        """, (
            pair['id'],
            pair['token0']['id'],
            pair['token1']['id'],
            reserve0,
            reserve1,
            Decimal(pair['reserveUSD']),
            calculated_price
        ))
        logging.info(f"Inserted/Updated V2 pair: {pair['id']}, Calculated Price: {calculated_price}")
    except Exception as e:
        logging.error(f"Error inserting/updating V2 pair {pair['id']}: {str(e)}")

async def process_pool(session, cur, pool):
    token0, token1 = pool[1], pool[2]
    v2_pairs = await fetch_v2_pair(session, token0, token1)
    
    if v2_pairs:
        for pair in v2_pairs:
            await insert_or_update_v2_pair(cur, pair)
    else:
        logging.info(f"No V2 pair found for tokens {token0} and {token1}")

async def update_v2_pairs():
    while True:
        start_time = datetime.now()
        async with aiohttp.ClientSession() as session:
            pool = await aiomysql.create_pool(**DB_CONFIG)
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    try:
                        # Fetch all V3 pools
                        await cur.execute("SELECT pool_address, token0_address, token1_address FROM uniswap_v3_pools")
                        v3_pools = await cur.fetchall()

                        # Process pools in batches
                        batch_size = 100
                        for i in range(0, len(v3_pools), batch_size):
                            batch = v3_pools[i:i+batch_size]
                            await asyncio.gather(*[process_pool(session, cur, pool) for pool in batch])
                            await conn.commit()
                            logging.info(f"Processed batch {i//batch_size + 1}/{(len(v3_pools) + batch_size - 1) // batch_size}")

                        logging.info("Database update completed successfully.")
                    except Exception as e:
                        logging.error(f"Error in main execution: {str(e)}")
                        await conn.rollback()
                    finally:
                        pool.close()
                        await pool.wait_closed()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logging.info(f"Update cycle completed in {duration} seconds")

        # Wait for 5 minutes before starting the next cycle
        await asyncio.sleep(300)

if __name__ == "__main__":
    asyncio.run(update_v2_pairs())