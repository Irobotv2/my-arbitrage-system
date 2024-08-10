import asyncio
import json
import logging
from itertools import cycle
import random

import aiohttp
import redis.asyncio as redis
from web3 import Web3
from web3.middleware import geth_poa_middleware

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
w3 = Web3(Web3.HTTPProvider('http://localhost:8545'))
w3.middleware_onion.inject(geth_poa_middleware, layer=0)

# ABIs
UNISWAP_V2_FACTORY_ABI = json.loads('[{"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"}],"name":"getPair","outputs":[{"internalType":"address","name":"pair","type":"address"}],"stateMutability":"view","type":"function"}]')
UNISWAP_V3_FACTORY_ABI = json.loads('[{"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"},{"internalType":"uint24","name":"fee","type":"uint24"}],"name":"getPool","outputs":[{"internalType":"address","name":"pool","type":"address"}],"stateMutability":"view","type":"function"}]')
ERC20_ABI = json.loads('[{"constant":true,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"type":"function"},{"constant":true,"inputs":[],"name":"name","outputs":[{"name":"","type":"string"}],"type":"function"},{"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"}]')

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_next_api_key():
    return next(api_key_cycle)

async def call_etherscan_api(session, url, max_retries=5):
    for attempt in range(max_retries):
        api_key = get_next_api_key()
        full_url = f"{url}&apikey={api_key}"
        async with session.get(full_url) as response:
            if response.status == 200:
                data = await response.json()
                if data['status'] == '1':
                    return data
                elif data['status'] == '0':
                    logger.warning(f"API request failed: {data['message']}")
            elif response.status == 502:
                logger.warning(f"Received 502 error. Retrying...")
            else:
                logger.warning(f"API request failed with status code {response.status}")
        
        wait_time = (2 ** attempt) + random.uniform(0, 1)
        logger.info(f"Retrying in {wait_time:.2f} seconds...")
        await asyncio.sleep(wait_time)
    
    raise Exception("Failed to get a successful response after multiple attempts")

def get_token_info(token_address):
    try:
        token_contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
        symbol = token_contract.functions.symbol().call()
        name = token_contract.functions.name().call()
        decimals = token_contract.functions.decimals().call()
        
        v2_pairs = get_uniswap_v2_pairs(token_address)
        v3_pools = get_uniswap_v3_pools(token_address)
        
        return {
            'address': token_address,
            'symbol': symbol,
            'name': name,
            'decimals': decimals,
            'v2_pairs': v2_pairs,
            'v3_pools': v3_pools
        }
    except Exception as e:
        logger.error(f"Error fetching token info for {token_address}: {str(e)}")
        return {
            'address': token_address,
            'symbol': 'UNKNOWN',
            'name': 'Unknown Token',
            'decimals': 18,
            'v2_pairs': [],
            'v3_pools': []
        }

def get_uniswap_v2_pairs(token_address):
    factory_contract = w3.eth.contract(address=UNISWAP_V2_FACTORY, abi=UNISWAP_V2_FACTORY_ABI)
    common_tokens = ['0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48', '0x6B175474E89094C44Da98b954EedeAC495271d0F']
    pairs = []
    for other_token in common_tokens:
        if other_token != token_address:
            pair_address = factory_contract.functions.getPair(token_address, other_token).call()
            if pair_address != '0x0000000000000000000000000000000000000000':
                pairs.append({'pair_address': pair_address, 'token0': token_address, 'token1': other_token})
    return pairs

def get_uniswap_v3_pools(token_address):
    factory_contract = w3.eth.contract(address=UNISWAP_V3_FACTORY, abi=UNISWAP_V3_FACTORY_ABI)
    common_tokens = ['0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48', '0x6B175474E89094C44Da98b954EedeAC495271d0F']
    fee_tiers = [500, 3000, 10000]
    pools = []
    for other_token in common_tokens:
        if other_token != token_address:
            for fee in fee_tiers:
                pool_address = factory_contract.functions.getPool(token_address, other_token, fee).call()
                if pool_address != '0x0000000000000000000000000000000000000000':
                    pools.append({'pool_address': pool_address, 'token0': token_address, 'token1': other_token, 'fee': fee})
    return pools

async def update_redis_with_token_data(token_info):
    token_key = f"token:{token_info['address']}"
    await redis_client.hset(token_key, mapping={
        'address': token_info['address'],
        'symbol': token_info['symbol'],
        'name': token_info['name'],
        'decimals': str(token_info['decimals'])
    })

    for pair in token_info['v2_pairs']:
        pair_key = f"uniswap_v2_pair:{pair['pair_address']}"
        await redis_client.hset(pair_key, mapping={
            'pair_address': pair['pair_address'],
            'token0': pair['token0'],
            'token1': pair['token1']
        })

    for pool in token_info['v3_pools']:
        pool_key = f"uniswap_v3_pool:{pool['pool_address']}"
        await redis_client.hset(pool_key, mapping={
            'pool_address': pool['pool_address'],
            'token0': pool['token0'],
            'token1': pool['token1'],
            'fee': str(pool['fee'])
        })

async def fetch_and_store_token_data(token_address):
    token_info = get_token_info(token_address)
    await update_redis_with_token_data(token_info)
    logger.info(f"Stored data for token: {token_info['symbol']} ({token_info['address']})")

async def clear_redis():
    logger.info("Clearing Redis database")
    await redis_client.flushdb()

async def main():
    try:
        logger.info("Starting token data insertion process")
        
        await clear_redis()

        # List of tokens to fetch (you can expand this list)
        tokens_to_fetch = [
            '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',  # WETH
            '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48',  # USDC
            '0x6B175474E89094C44Da98b954EedeAC495271d0F',  # DAI
            # Add more token addresses here
        ]

        for token_address in tokens_to_fetch:
            await fetch_and_store_token_data(token_address)

        logger.info("Token data insertion complete")
    finally:
        logger.info("Closing connections")
        await redis_client.aclose()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Script terminated by user")
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")