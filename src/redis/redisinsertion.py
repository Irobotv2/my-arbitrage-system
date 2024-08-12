import asyncio
import json
import logging
from itertools import cycle
import random
import time

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

class RateLimiter:
    def __init__(self, calls, period):
        self.calls = calls
        self.period = period
        self.timestamps = []

    async def wait(self):
        now = time.time()
        self.timestamps = [t for t in self.timestamps if now - t < self.period]
        if len(self.timestamps) >= self.calls:
            sleep_time = self.period - (now - self.timestamps[0])
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
        self.timestamps.append(time.time())

# Initialize the rate limiter
etherscan_limiter = RateLimiter(calls=5, period=1)  # 5 calls per second

def get_next_api_key():
    return next(api_key_cycle)

async def fetch_top_tokens_from_etherscan(n=100):
    url = "https://api.etherscan.io/api"
    params = {
        "module": "account",
        "action": "tokentx",
        "address": "0x0000000000000000000000000000000000000000",  # Use a dummy address
        "startblock": 0,
        "endblock": 999999999,
        "sort": "desc",
        "apikey": get_next_api_key()
    }
    async with aiohttp.ClientSession() as session:
        await etherscan_limiter.wait()  # Wait for rate limit
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                logger.info(f"Etherscan API response: {data}")  # Log the entire response
                if data["status"] == "1":
                    transactions = data["result"]
                    unique_tokens = set()
                    tokens = []
                    for tx in transactions:
                        token_address = Web3.to_checksum_address(tx["contractAddress"])
                        if token_address not in unique_tokens and len(tokens) < n:
                            unique_tokens.add(token_address)
                            tokens.append({"symbol": tx["tokenSymbol"], "address": token_address})
                    logger.info(f"Successfully fetched {len(tokens)} tokens from Etherscan")
                    return tokens
                else:
                    logger.error(f"Etherscan API error: {data.get('message', 'Unknown error')}")
                    logger.error(f"Full error response: {data}")
            else:
                logger.error(f"Failed to fetch tokens from Etherscan. Status code: {response.status}")
                logger.error(f"Response text: {await response.text()}")
    return []

def get_token_info(token_address):
    try:
        # Convert the address to checksum format
        checksum_address = Web3.to_checksum_address(token_address)
        
        token_contract = w3.eth.contract(address=checksum_address, abi=ERC20_ABI)
        
        # Use exception handling for each call in case one fails
        try:
            symbol = token_contract.functions.symbol().call()
        except Exception as e:
            logger.warning(f"Failed to get symbol for {checksum_address}: {str(e)}")
            symbol = "UNKNOWN"

        try:
            name = token_contract.functions.name().call()
        except Exception as e:
            logger.warning(f"Failed to get name for {checksum_address}: {str(e)}")
            name = "Unknown Token"

        try:
            decimals = token_contract.functions.decimals().call()
        except Exception as e:
            logger.warning(f"Failed to get decimals for {checksum_address}: {str(e)}")
            decimals = 18

        v2_pairs = get_uniswap_v2_pairs(checksum_address)
        v3_pools = get_uniswap_v3_pools(checksum_address)
        
        return {
            'address': checksum_address,
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
    try:
        token_info = get_token_info(token_address)
        await update_redis_with_token_data(token_info)
        logger.info(f"Stored data for token: {token_info['symbol']} ({token_info['address']})")
    except Exception as e:
        logger.error(f"Failed to fetch and store data for token address {token_address}: {str(e)}")

async def clear_redis():
    logger.info("Clearing Redis database")
    await redis_client.flushdb()

async def generate_token_pairs():
    """Generate all possible token pairs with WETH"""
    weth = '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'
    tokens = await redis_client.keys("token:*")
    token_addresses = [token.split(':')[1] for token in tokens if token.split(':')[1] != weth]
    return [(weth, token) for token in token_addresses]

async def store_token_pairs():
    """Store generated token pairs in Redis"""
    pairs = await generate_token_pairs()
    for i, (token1, token2) in enumerate(pairs):
        pair_key = f"token_pair:{i}"
        await redis_client.hset(pair_key, mapping={
            'token1': token1,
            'token2': token2
        })
    logger.info(f"Stored {len(pairs)} token pairs in Redis")

async def main():
    try:
        logger.info("Starting token data insertion and pair generation process")
        
        await clear_redis()

        # Fetch top tokens from Etherscan
        top_tokens = await fetch_top_tokens_from_etherscan(100)
        
        # Hardcoded tokens
        hardcoded_tokens = [
            {'symbol': 'WETH', 'address': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'},
            {'symbol': 'USDC', 'address': '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'},
            {'symbol': 'DAI', 'address': '0x6B175474E89094C44Da98b954EedeAC495271d0F'},
        ]

        # Combine hardcoded tokens and top tokens
        all_tokens = hardcoded_tokens + top_tokens

        # Process all tokens
        for token in all_tokens:
            if token['address']:  # Only process tokens with a valid address
                await fetch_and_store_token_data(token['address'])
                await asyncio.sleep(0.2)  # Add a 0.2-second delay between each token (5 per second)

        # Generate and store token pairs
        await store_token_pairs()

        logger.info("Token data insertion and pair generation complete")
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