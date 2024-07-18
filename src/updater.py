import asyncio
from web3 import AsyncWeb3
import aiomysql
import logging
from decimal import Decimal, getcontext
from web3.exceptions import ContractLogicError, BadFunctionCallOutput

# Set higher precision for Decimal calculations
getcontext().prec = 30

# Configure logging
logging.basicConfig(filename='update_uniswap.log', level=logging.INFO,
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

# ABIs
UNI_V2_ABI = [{"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"stateMutability":"view","type":"function"}]
UNI_V3_ABI = [{"inputs":[],"name":"slot0","outputs":[{"internalType":"uint160","name":"sqrtPriceX96","type":"uint160"},{"internalType":"int24","name":"tick","type":"int24"},{"internalType":"uint16","name":"observationIndex","type":"uint16"},{"internalType":"uint16","name":"observationCardinality","type":"uint16"},{"internalType":"uint16","name":"observationCardinalityNext","type":"uint16"},{"internalType":"uint8","name":"feeProtocol","type":"uint8"},{"internalType":"bool","name":"unlocked","type":"bool"}],"stateMutability":"view","type":"function"}]

# Set to store consistently failing pairs
failing_pairs = set()

async def is_contract_valid(web3, address):
    code = await web3.eth.get_code(web3.to_checksum_address(address))
    return len(code) > 2  # '0x' is returned for non-contract addresses

async def fetch_uniswap_v2_data(web3, pair_address, max_retries=3):
    if not await is_contract_valid(web3, pair_address):
        raise ValueError(f"No contract found at address {pair_address}")
    
    contract = web3.eth.contract(address=web3.to_checksum_address(pair_address), abi=UNI_V2_ABI)
    for attempt in range(max_retries):
        try:
            reserves = await contract.functions.getReserves().call()
            return reserves[0], reserves[1]
        except (ContractLogicError, BadFunctionCallOutput) as e:
            if attempt == max_retries - 1:
                logging.error(f"Error fetching V2 pair {pair_address}: {type(e).__name__}: {str(e)}")
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
        except Exception as e:
            logging.error(f"Unexpected error fetching V2 pair {pair_address}: {type(e).__name__}: {str(e)}")
            raise

async def fetch_uniswap_v3_data(web3, pool_address, max_retries=3):
    contract = web3.eth.contract(address=web3.to_checksum_address(pool_address), abi=UNI_V3_ABI)
    for attempt in range(max_retries):
        try:
            slot0 = await contract.functions.slot0().call()
            return slot0[0], slot0[1]
        except (ContractLogicError, BadFunctionCallOutput) as e:
            if attempt == max_retries - 1:
                logging.error(f"Error fetching V3 pool {pool_address}: {type(e).__name__}: {str(e)}")
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
        except Exception as e:
            logging.error(f"Unexpected error fetching V3 pool {pool_address}: {type(e).__name__}: {str(e)}")
            raise

async def update_uniswap_data(conn, web3, v2_pairs, v3_pools):
    async with conn.cursor() as cur:
        latest_block = await web3.eth.get_block('latest')
        block_number, block_timestamp = latest_block['number'], latest_block['timestamp']

        # Update V2 pairs
        for pair in v2_pairs:
            if pair[0] in failing_pairs:
                continue
            try:
                reserve0, reserve1 = await fetch_uniswap_v2_data(web3, pair[0])
                price = Decimal(reserve1) / Decimal(reserve0) if reserve0 != 0 else 0
                await cur.execute("""
                    UPDATE uniswap_v2_pairs 
                    SET reserve0 = %s, reserve1 = %s, 
                        last_block_number = %s, last_block_timestamp = %s,
                        last_sync = NOW(), calculated_price = %s
                    WHERE pair_address = %s
                """, (str(reserve0), str(reserve1), block_number, block_timestamp, str(price), pair[0]))
            except Exception as e:
                logging.error(f"Error updating V2 pair {pair[0]}: {e}")
                failing_pairs.add(pair[0])

        # Update V3 pools
        for pool in v3_pools:
            try:
                sqrt_price_x96, tick = await fetch_uniswap_v3_data(web3, pool[0])
                price = (Decimal(sqrt_price_x96) / Decimal(2**96)) ** 2
                await cur.execute("""
                    UPDATE uniswap_v3_pools 
                    SET sqrt_price = %s, 
                        current_tick = %s,
                        last_block_number = %s, 
                        last_block_timestamp = %s,
                        calculated_price = %s
                    WHERE pool_address = %s
                """, (str(sqrt_price_x96), tick, block_number, block_timestamp, str(price), pool[0]))
            except Exception as e:
                logging.error(f"Error updating V3 pool {pool[0]}: {e}")

async def remove_invalid_pairs(conn, web3):
    async with conn.cursor() as cur:
        await cur.execute("SELECT pair_address FROM uniswap_v2_pairs")
        all_pairs = await cur.fetchall()
        
        for pair in all_pairs:
            if not await is_contract_valid(web3, pair[0]):
                logging.warning(f"Invalid contract found: {pair[0]}. Removing from database.")
                await cur.execute("DELETE FROM uniswap_v2_pairs WHERE pair_address = %s", (pair[0],))
        
        await conn.commit()

async def main():
    pool = await aiomysql.create_pool(**DB_CONFIG)
    web3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(TENDERLY_RPC_URL))
    
    # Remove invalid pairs at startup
    async with pool.acquire() as conn:
        await remove_invalid_pairs(conn, web3)
    
    while True:
        start_time = asyncio.get_event_loop().time()
        logging.info("Starting update cycle...")
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT pair_address FROM uniswap_v2_pairs WHERE pair_address NOT IN %s", (tuple(failing_pairs) or ('',),))
                    v2_pairs = await cur.fetchall()
                    await cur.execute("SELECT pool_address FROM uniswap_v3_pools")
                    v3_pools = await cur.fetchall()

                await update_uniswap_data(conn, web3, v2_pairs, v3_pools)
                await conn.commit()
        
            end_time = asyncio.get_event_loop().time()
            duration = end_time - start_time
            logging.info(f"Update cycle completed in {duration:.2f} seconds. Processed {len(v2_pairs)} V2 pairs and {len(v3_pools)} V3 pools.")

            sleep_time = max(10 - duration, 0)  # Ensure we don't sleep for negative time
            logging.info(f"Sleeping for {sleep_time:.2f} seconds...")
            await asyncio.sleep(sleep_time)
        except Exception as e:
            logging.error(f"An error occurred during the update cycle: {e}")
            await asyncio.sleep(10)  # Wait before retrying

if __name__ == "__main__":
    asyncio.run(main())
