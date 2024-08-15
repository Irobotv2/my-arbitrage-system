import asyncio
import json
import logging
from decimal import Decimal
import time

import redis.asyncio as redis
from web3 import Web3
from web3.middleware import geth_poa_middleware

# Configuration
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_DB = 0
UPDATE_INTERVAL = 0.1  # Update every 60 seconds

# Initialize Redis
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

# Initialize Web3 with localhost node
w3 = Web3(Web3.HTTPProvider('http://localhost:8545'))
w3.middleware_onion.inject(geth_poa_middleware, layer=0)

# ABIs
UNISWAP_V2_PAIR_ABI = json.loads('[{"constant":true,"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"payable":false,"stateMutability":"view","type":"function"}]')
UNISWAP_V3_POOL_ABI = json.loads('[{"inputs":[],"name":"slot0","outputs":[{"internalType":"uint160","name":"sqrtPriceX96","type":"uint160"},{"internalType":"int24","name":"tick","type":"int24"},{"internalType":"uint16","name":"observationIndex","type":"uint16"},{"internalType":"uint16","name":"observationCardinality","type":"uint16"},{"internalType":"uint16","name":"observationCardinalityNext","type":"uint16"},{"internalType":"uint8","name":"feeProtocol","type":"uint8"},{"internalType":"bool","name":"unlocked","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"liquidity","outputs":[{"internalType":"uint128","name":"","type":"uint128"}],"stateMutability":"view","type":"function"}]')

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def update_v2_pair_data(pair_address):
    try:
        pair_contract = w3.eth.contract(address=pair_address, abi=UNISWAP_V2_PAIR_ABI)
        reserves = pair_contract.functions.getReserves().call()
        reserve0, reserve1, _ = reserves

        # Calculate price (use reserve1/reserve0 as a simple price representation)
        price = reserve1 / reserve0 if reserve0 != 0 else 0

        await redis_client.hset(f"uniswap_v2_pair:{pair_address}", mapping={
            'reserve0': str(reserve0),
            'reserve1': str(reserve1),
            'price': str(price)
        })
        logger.info(f"Updated V2 pair {pair_address}")
    except Exception as e:
        logger.error(f"Error updating V2 pair {pair_address}: {str(e)}")

async def update_v3_pool_data(pool_address):
    try:
        pool_contract = w3.eth.contract(address=pool_address, abi=UNISWAP_V3_POOL_ABI)
        slot0 = pool_contract.functions.slot0().call()
        liquidity = pool_contract.functions.liquidity().call()

        await redis_client.hset(f"uniswap_v3_pool:{pool_address}", mapping={
            'sqrtPriceX96': str(slot0[0]),
            'liquidity': str(liquidity)
        })
        logger.info(f"Updated V3 pool {pool_address}")
    except Exception as e:
        logger.error(f"Error updating V3 pool {pool_address}: {str(e)}")

async def update_all_pools():
    v2_pairs = await redis_client.keys("uniswap_v2_pair:*")
    v3_pools = await redis_client.keys("uniswap_v3_pool:*")

    v2_tasks = [update_v2_pair_data(pair.split(':')[1]) for pair in v2_pairs]
    v3_tasks = [update_v3_pool_data(pool.split(':')[1]) for pool in v3_pools]

    await asyncio.gather(*v2_tasks, *v3_tasks)

async def main():
    while True:
        start_time = time.time()
        logger.info("Starting pool data update...")
        await update_all_pools()
        logger.info("Pool data update completed.")
        
        elapsed_time = time.time() - start_time
        sleep_time = max(0, UPDATE_INTERVAL - elapsed_time)
        logger.info(f"Sleeping for {sleep_time:.2f} seconds...")
        await asyncio.sleep(sleep_time)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Script terminated by user")
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")