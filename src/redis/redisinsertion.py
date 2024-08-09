import asyncio
import json
import logging
from itertools import cycle

import aiohttp
import redis.asyncio as redis
from web3 import AsyncWeb3, AsyncHTTPProvider
from web3.contract import AsyncContract
from web3.middleware import geth_poa_middleware

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='uniswap_data_script.log', filemode='a')
logger = logging.getLogger(__name__)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
logger.addHandler(console_handler)

# Configuration
API_KEYS = [
    "NZRMMNNMNFYZGV63IISNNND63M3SSEFTIK",
    "C29QY5P9151ZTIQDWJB3WPN3NC2VHMQ8F7",
    "N9WVZWZMMTUIM8DPS6Y32WWAQKT2JEYHGN"
]
api_key_cycle = cycle(API_KEYS)

UNISWAP_V2_FACTORY = "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"
UNISWAP_V3_FACTORY = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_DB = 0

# Initialize Redis
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

# Initialize Web3 with localhost node
w3 = AsyncWeb3(AsyncHTTPProvider('http://localhost:8545'))
w3.middleware_onion.inject(geth_poa_middleware, layer=0)

# ABIs
UNISWAP_V2_PAIR_ABI = json.loads('[{"constant":true,"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"payable":false,"stateMutability":"view","type":"function"}]')
UNISWAP_V3_POOL_ABI = json.loads('[{"inputs":[],"name":"slot0","outputs":[{"internalType":"uint160","name":"sqrtPriceX96","type":"uint160"},{"internalType":"int24","name":"tick","type":"int24"},{"internalType":"uint16","name":"observationIndex","type":"uint16"},{"internalType":"uint16","name":"observationCardinality","type":"uint16"},{"internalType":"uint16","name":"observationCardinalityNext","type":"uint16"},{"internalType":"uint8","name":"feeProtocol","type":"uint8"},{"internalType":"bool","name":"unlocked","type":"bool"}],"stateMutability":"view","type":"function"}]')
ERC20_ABI = json.loads('[{"constant":true,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"type":"function"},{"constant":true,"inputs":[],"name":"name","outputs":[{"name":"","type":"string"}],"type":"function"}]')

def get_next_api_key():
    return next(api_key_cycle)

async def call_etherscan_api(session, url):
    for _ in range(3):  # Try up to 3 times
        api_key = get_next_api_key()
        full_url = f"{url}&apikey={api_key}"
        async with session.get(full_url) as response:
            if response.status == 200:
                return await response.json()
            elif response.status == 502:
                logger.warning(f"Received 502 error. Retrying with a different API key...")
                await asyncio.sleep(1)  # Wait a bit before retrying
            else:
                raise Exception(f"API request failed with status code {response.status}")
    raise Exception("Failed to get a successful response after 3 attempts")

async def fetch_logs(session, url, topic0):
    all_logs = []
    from_block = 0
    to_block = 'latest'
    
    while True:
        current_url = f"{url}&fromBlock={from_block}&toBlock={to_block}"
        try:
            data = await call_etherscan_api(session, current_url)
            
            if 'result' not in data or not isinstance(data['result'], list):
                logger.error(f"Unexpected API response: {data}")
                break

            logs = data['result']
            all_logs.extend(logs)
            
            if len(logs) < 1000:  # If we get less than 1000 results, we've reached the end
                break
            
            # Update from_block for the next iteration
            from_block = int(logs[-1]['blockNumber'], 16) + 1
            
            logger.info(f"Fetched {len(all_logs)} logs so far...")
            await asyncio.sleep(0.1)  # Small delay between requests
        except Exception as e:
            logger.error(f"Error fetching logs: {e}")
            await asyncio.sleep(1)  # Wait a bit longer on error
    
    return all_logs

async def get_token_info(token_address):
    try:
        token_contract = AsyncContract(address=token_address, abi=ERC20_ABI, w3=w3)
        symbol, name = await asyncio.gather(
            token_contract.functions.symbol().call(),
            token_contract.functions.name().call()
        )
        return {'symbol': symbol, 'name': name}
    except Exception as e:
        logger.error(f"Error fetching token info for {token_address}: {str(e)}")
        return {'symbol': 'UNKNOWN', 'name': 'Unknown Token'}

async def fetch_one_uniswap_v2_pair(session):
    url = f"https://api.etherscan.io/api?module=logs&action=getLogs&address={UNISWAP_V2_FACTORY}&topic0=0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9&limit=1"
    logs = await fetch_logs(session, url, "0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9")

    if logs:
        log = logs[0]
        pair_address = AsyncWeb3.to_checksum_address('0x' + log['data'][26:66])
        token0 = AsyncWeb3.to_checksum_address('0x' + log['topics'][1][26:])
        token1 = AsyncWeb3.to_checksum_address('0x' + log['topics'][2][26:])
        
        token0_info = await get_token_info(token0)
        token1_info = await get_token_info(token1)
        
        return {
            'pair_address': pair_address,
            'token0': token0,
            'token0_symbol': token0_info['symbol'],
            'token0_name': token0_info['name'],
            'token1': token1,
            'token1_symbol': token1_info['symbol'],
            'token1_name': token1_info['name']
        }
    return None

async def fetch_one_uniswap_v3_pool(session):
    url = f"https://api.etherscan.io/api?module=logs&action=getLogs&address={UNISWAP_V3_FACTORY}&topic0=0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118&limit=1"
    logs = await fetch_logs(session, url, "0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118")

    if logs:
        log = logs[0]
        pool_address = AsyncWeb3.to_checksum_address('0x' + log['data'][26:66])
        token0 = AsyncWeb3.to_checksum_address('0x' + log['topics'][1][26:])
        token1 = AsyncWeb3.to_checksum_address('0x' + log['topics'][2][26:])
        fee = int(log['topics'][3], 16)
        
        token0_info = await get_token_info(token0)
        token1_info = await get_token_info(token1)
        
        return {
            'pool_address': pool_address,
            'token0': token0,
            'token0_symbol': token0_info['symbol'],
            'token0_name': token0_info['name'],
            'token1': token1,
            'token1_symbol': token1_info['symbol'],
            'token1_name': token1_info['name'],
            'fee': fee
        }
    return None

async def update_redis_with_data(v2_pair, v3_pool):
    logger.info("Starting to update Redis with fetched data")

    if v2_pair:
        key = f"uniswap_v2_pairs:{v2_pair['pair_address']}"
        data = {
            'token0_address': v2_pair['token0'],
            'token0_symbol': v2_pair['token0_symbol'],
            'token0_name': v2_pair['token0_name'],
            'token1_address': v2_pair['token1'],
            'token1_symbol': v2_pair['token1_symbol'],
            'token1_name': v2_pair['token1_name'],
            'pair_address': v2_pair['pair_address']
        }
        await redis_client.hset(key, mapping=data)
        logger.info(f"Added V2 pair: {v2_pair['pair_address']} ({v2_pair['token0_symbol']}-{v2_pair['token1_symbol']})")

    if v3_pool:
        key = f"uniswap_v3_pools:{v3_pool['pool_address']}"
        data = {
            'token0_address': v3_pool['token0'],
            'token0_symbol': v3_pool['token0_symbol'],
            'token0_name': v3_pool['token0_name'],
            'token1_address': v3_pool['token1'],
            'token1_symbol': v3_pool['token1_symbol'],
            'token1_name': v3_pool['token1_name'],
            'pool_address': v3_pool['pool_address'],
            'fee_tier': str(v3_pool['fee'])
        }
        await redis_client.hset(key, mapping=data)
        logger.info(f"Added V3 pool: {v3_pool['pool_address']} ({v3_pool['token0_symbol']}-{v3_pool['token1_symbol']})")

async def clear_redis():
    logger.info("Clearing Redis database")
    await redis_client.flushdb()

async def main():
    logger.info("Starting Uniswap data pull process")
    
    await clear_redis()
    
    async with aiohttp.ClientSession() as session:
        # Fetch initial data
        v2_pair = await fetch_one_uniswap_v2_pair(session)
        v3_pool = await fetch_one_uniswap_v3_pool(session)

        # Update Redis with fetched data
        await update_redis_with_data(v2_pair, v3_pool)

    logger.info("Initial data pull and Redis update complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Script terminated by user")
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
    finally:
        logger.info("Closing connections")
        asyncio.run(asyncio.sleep(0))  # Allow event loop to complete pending tasks
        asyncio.run(redis_client.aclose())  # Use aclose() instead of close()