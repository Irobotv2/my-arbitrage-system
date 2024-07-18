import asyncio
from web3 import AsyncWeb3
import aiomysql
import logging
from decimal import Decimal, getcontext
from aiohttp import ClientSession

# Set higher precision for Decimal calculations
getcontext().prec = 80

# Configure logging
logging.basicConfig(filename='/home/irobot/projects/my-arbitrage-system/src/updateuv3.log', 
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

# Tenderly RPC URL
TENDERLY_RPC_URL = 'https://mainnet.gateway.tenderly.co/4XuvSWbosReD6ZCdS5naXU'

# Uniswap V3 Pool ABI (simplified)
UNI_V3_ABI = [{"inputs":[],"name":"slot0","outputs":[{"internalType":"uint160","name":"sqrtPriceX96","type":"uint160"},{"internalType":"int24","name":"tick","type":"int24"},{"internalType":"uint16","name":"observationIndex","type":"uint16"},{"internalType":"uint16","name":"observationCardinality","type":"uint16"},{"internalType":"uint16","name":"observationCardinalityNext","type":"uint16"},{"internalType":"uint8","name":"feeProtocol","type":"uint8"},{"internalType":"bool","name":"unlocked","type":"bool"}],"stateMutability":"view","type":"function"}]

def format_price(price):
    if abs(price) < 1e-10:
        return f"{price:.30f}"
    elif abs(price) > 1e10:
        return f"{price:.2f}"
    else:
        return f"{price:.18f}"

async def fetch_uniswap_v3_data(session, web3, pool_address):
    checksum_address = web3.to_checksum_address(pool_address)
    contract = web3.eth.contract(address=checksum_address, abi=UNI_V3_ABI)
    slot0 = await contract.functions.slot0().call()
    return slot0[0], slot0[1]

async def update_pool(session, web3, pool_address, block_number, block_timestamp):
    try:
        sqrt_price_x96, tick = await fetch_uniswap_v3_data(session, web3, pool_address)
        
        sqrt_price = Decimal(sqrt_price_x96)
        price = (sqrt_price / Decimal(2**96)) ** 2
        volume_24h_usd = 0  # Placeholder

        formatted_price = format_price(price)

        logging.info(f"Fetched data for pool {pool_address} at block {block_number}: sqrt_price={sqrt_price}, tick={tick}, price={formatted_price}")
        return (pool_address, str(sqrt_price), tick, block_number, block_timestamp, formatted_price, str(volume_24h_usd))
    except Exception as e:
        logging.error(f"Error fetching data for pool {pool_address}: {e}")
        return None

async def update_uniswap_v3_data(db_pool, web3):
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT pool_address FROM uniswap_v3_pools")
            pools = await cur.fetchall()

    # Fetch latest block once for all updates
    latest_block = await web3.eth.get_block('latest')
    block_number, block_timestamp = latest_block['number'], latest_block['timestamp']

    async with ClientSession() as session:
        tasks = [update_pool(session, web3, pool[0], block_number, block_timestamp) for pool in pools]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            for result in results:
                if result is not None and not isinstance(result, Exception):
                    try:
                        await cur.execute("""
                            UPDATE uniswap_v3_pools 
                            SET sqrt_price = %s, 
                                current_tick = %s,
                                last_block_number = %s, 
                                last_block_timestamp = %s,
                                calculated_price = %s,
                                volume_24h_usd = %s
                            WHERE pool_address = %s
                        """, result[1:] + (result[0],))
                    except aiomysql.Error as e:
                        logging.error(f"Error updating pool {result[0]}: {e}")
        
        await conn.commit()
        logging.info(f"Update committed for {len([r for r in results if r is not None])} pools.")

async def main():
    db_pool = await aiomysql.create_pool(**DB_CONFIG)
    web3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(TENDERLY_RPC_URL))
    
    while True:
        start_time = asyncio.get_event_loop().time()
        logging.info("Starting update cycle...")
        await update_uniswap_v3_data(db_pool, web3)
        end_time = asyncio.get_event_loop().time()
        duration = end_time - start_time
        logging.info(f"Update cycle completed in {duration:.2f} seconds.")
        
        sleep_time = max(10 - duration, 0)  # Ensure we don't sleep for negative time
        logging.info(f"Sleeping for {sleep_time:.2f} seconds...")
        await asyncio.sleep(sleep_time)

if __name__ == "__main__":
    asyncio.run(main())
