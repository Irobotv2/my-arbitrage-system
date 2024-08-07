import asyncio
import numpy as np
from web3 import Web3
from web3.providers.websocket import WebsocketProvider
from datetime import datetime
import ujson
import logging
import time
from websockets import connect
from cachetools import TTLCache
from concurrent.futures import ProcessPoolExecutor

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ethereum node URL
ETH_NODE_URL = "wss://mainnet.infura.io/ws/v3/0640f56f05a942d7a25cfeff50de344d"

# Web3 instance
w3 = Web3(WebsocketProvider(ETH_NODE_URL))

# Contract addresses
UNISWAP_V2_PAIR_ADDRESS = "0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc"
UNISWAP_V3_POOL_ADDRESS = "0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8"

# ABI (Application Binary Interface) for the contracts
UNISWAP_V2_PAIR_ABI = [{"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"stateMutability":"view","type":"function"}]
UNISWAP_V3_POOL_ABI = [{"inputs":[],"name":"slot0","outputs":[{"internalType":"uint160","name":"sqrtPriceX96","type":"uint160"},{"internalType":"int24","name":"tick","type":"int24"},{"internalType":"uint16","name":"observationIndex","type":"uint16"},{"internalType":"uint16","name":"observationCardinality","type":"uint16"},{"internalType":"uint16","name":"observationCardinalityNext","type":"uint16"},{"internalType":"uint8","name":"feeProtocol","type":"uint8"},{"internalType":"bool","name":"unlocked","type":"bool"}],"stateMutability":"view","type":"function"}]

# Contract instances
uniswap_v2_pair = w3.eth.contract(address=UNISWAP_V2_PAIR_ADDRESS, abi=UNISWAP_V2_PAIR_ABI)
uniswap_v3_pool = w3.eth.contract(address=UNISWAP_V3_POOL_ADDRESS, abi=UNISWAP_V3_POOL_ABI)

# Price cache
price_cache = TTLCache(maxsize=100, ttl=1)  # Cache for 1 second

# Process pool for parallel calculations
process_pool = ProcessPoolExecutor(max_workers=2)

async def get_latest_block():
    async with connect(ETH_NODE_URL) as ws:
        await ws.send(ujson.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_subscribe",
            "params": ["newHeads"]
        }))
        
        while True:
            message = await ws.recv()
            data = ujson.loads(message)
            if 'params' in data and 'result' in data['params']:
                new_block = data['params']['result']
                yield new_block

async def get_cached_price(dex, query_func):
    cache_key = f"{dex}"
    if cache_key in price_cache:
        return price_cache[cache_key]
    
    price_data = await query_func()
    price_cache[cache_key] = price_data
    return price_data

async def query_uniswap_v2():
    reserves = uniswap_v2_pair.functions.getReserves().call()
    return {
        'reserve0': reserves[0],
        'reserve1': reserves[1]
    }

async def query_uniswap_v3():
    slot0 = uniswap_v3_pool.functions.slot0().call()
    return {
        'sqrtPriceX96': slot0[0],
    }

def calculate_v2_price(reserve0, reserve1):
    return (np.float64(reserve0) / 1e6) / (np.float64(reserve1) / 1e18)

def calculate_v3_price(sqrtPriceX96):
    sqrt_price = np.float64(sqrtPriceX96)
    price = (sqrt_price / (2**96)) ** 2
    return 1 / price * 1e12

def validate_price(price, min_price=2000, max_price=5000):
    return min_price <= price <= max_price

def calculate_arbitrage(v2_price, v3_price):
    price_difference = abs(v2_price - v3_price)
    return (price_difference / min(v2_price, v3_price)) * 100

async def monitor_prices():
    async for block in get_latest_block():
        start_time = time.perf_counter()
        logger.info(f"New block: {block['number']}")

        try:
            v2_data, v3_data = await asyncio.gather(
                get_cached_price('uniswap_v2', query_uniswap_v2),
                get_cached_price('uniswap_v3', query_uniswap_v3)
            )

            if v2_data and v3_data:
                v2_price, v3_price = await asyncio.get_event_loop().run_in_executor(
                    process_pool,
                    calculate_v2_price, v2_data['reserve0'], v2_data['reserve1']
                ), await asyncio.get_event_loop().run_in_executor(
                    process_pool,
                    calculate_v3_price, v3_data['sqrtPriceX96']
                )

                if validate_price(v2_price) and validate_price(v3_price):
                    arbitrage_percentage = await asyncio.get_event_loop().run_in_executor(
                        process_pool,
                        calculate_arbitrage, v2_price, v3_price
                    )
                    if arbitrage_percentage > 0.1:  # Only log significant arbitrage opportunities
                        logger.info(f"Arbitrage opportunity: {arbitrage_percentage:.2f}%")
                else:
                    logger.warning(f"Prices outside expected range: V2={v2_price:.2f}, V3={v3_price:.2f}")
            else:
                logger.error("Failed to fetch data from Uniswap contracts")
        except Exception as e:
            logger.error(f"An error occurred: {e}")

        logger.info(f"Execution time: {(time.perf_counter() - start_time):.6f} seconds")

if __name__ == "__main__":
    asyncio.run(monitor_prices())