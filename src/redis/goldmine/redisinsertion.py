import asyncio
import json
import logging
from itertools import cycle
import time
from decimal import Decimal

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
ERC20_ABI = json.loads('[{"constant":true,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"type":"function"},{"constant":true,"inputs":[],"name":"name","outputs":[{"name":"","type":"string"}],"type":"function"},{"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"}]')
UNISWAP_V2_FACTORY_ABI = json.loads('[{"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"}],"name":"getPair","outputs":[{"internalType":"address","name":"pair","type":"address"}],"stateMutability":"view","type":"function"}]')
UNISWAP_V3_FACTORY_ABI = json.loads('[{"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"},{"internalType":"uint24","name":"fee","type":"uint24"}],"name":"getPool","outputs":[{"internalType":"address","name":"pool","type":"address"}],"stateMutability":"view","type":"function"}]')
UNISWAP_V2_PAIR_ABI = json.loads('[{"constant":true,"inputs":[],"name":"token0","outputs":[{"name":"","type":"address"}],"type":"function"},{"constant":true,"inputs":[],"name":"token1","outputs":[{"name":"","type":"address"}],"type":"function"},{"constant":true,"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"payable":false,"stateMutability":"view","type":"function"}]')
UNISWAP_V3_POOL_ABI = json.loads('[{"inputs":[],"name":"token0","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"token1","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"slot0","outputs":[{"internalType":"uint160","name":"sqrtPriceX96","type":"uint160"},{"internalType":"int24","name":"tick","type":"int24"},{"internalType":"uint16","name":"observationIndex","type":"uint16"},{"internalType":"uint16","name":"observationCardinality","type":"uint16"},{"internalType":"uint16","name":"observationCardinalityNext","type":"uint16"},{"internalType":"uint8","name":"feeProtocol","type":"uint8"},{"internalType":"bool","name":"unlocked","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"liquidity","outputs":[{"internalType":"uint128","name":"","type":"uint128"}],"stateMutability":"view","type":"function"}]')

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
                logger.info(f"Etherscan API response status: {data['status']}")
                
                if data["status"] == "1":
                    transactions = data["result"]
                    unique_tokens = set()
                    tokens = []
                    
                    for tx in transactions:
                        token_address = Web3.to_checksum_address(tx["contractAddress"])
                        if token_address not in unique_tokens and len(tokens) < n:
                            unique_tokens.add(token_address)
                            tokens.append({
                                "symbol": tx["tokenSymbol"],
                                "address": token_address,
                                "name": tx["tokenName"]
                            })
                    
                    logger.info(f"Successfully fetched {len(tokens)} unique tokens from Etherscan")
                    return tokens
                else:
                    logger.error(f"Etherscan API error: {data.get('message', 'Unknown error')}")
                    logger.error(f"Full error response: {data}")
            else:
                logger.error(f"Failed to fetch tokens from Etherscan. Status code: {response.status}")
                logger.error(f"Response text: {await response.text()}")
    
    return []  # Return an empty list if the fetch fails
def detect_contract_type(address):
    contract = w3.eth.contract(address=address, abi=ERC20_ABI)
    try:
        symbol = contract.functions.symbol().call()
        return 'ERC20'
    except:
        pass
    
    contract = w3.eth.contract(address=address, abi=UNISWAP_V2_PAIR_ABI)
    try:
        token0 = contract.functions.token0().call()
        return 'UNISWAP_V2_PAIR'
    except:
        pass
    
    contract = w3.eth.contract(address=address, abi=UNISWAP_V3_POOL_ABI)
    try:
        token0 = contract.functions.token0().call()
        return 'UNISWAP_V3_POOL'
    except:
        pass
    
    return 'UNKNOWN'

def get_token_info(token_address):
    try:
        checksum_address = Web3.to_checksum_address(token_address)
        contract_type = detect_contract_type(checksum_address)
        
        if contract_type == 'ERC20':
            contract = w3.eth.contract(address=checksum_address, abi=ERC20_ABI)
            symbol = contract.functions.symbol().call()
            name = contract.functions.name().call()
            decimals = contract.functions.decimals().call()
            
            v2_pairs = get_uniswap_v2_pairs(checksum_address)
            v3_pools = get_uniswap_v3_pools(checksum_address)
            
            return {
                'address': checksum_address,
                'symbol': symbol,
                'name': name,
                'decimals': decimals,
                'contract_type': contract_type,
                'v2_pairs': v2_pairs,
                'v3_pools': v3_pools
            }
        elif contract_type == 'UNISWAP_V2_PAIR':
            contract = w3.eth.contract(address=checksum_address, abi=UNISWAP_V2_PAIR_ABI)
            token0 = contract.functions.token0().call()
            token1 = contract.functions.token1().call()
            reserves = contract.functions.getReserves().call()
            
            return {
                'address': checksum_address,
                'token0': token0,
                'token1': token1,
                'reserve0': reserves[0],
                'reserve1': reserves[1],
                'contract_type': contract_type
            }
        elif contract_type == 'UNISWAP_V3_POOL':
            contract = w3.eth.contract(address=checksum_address, abi=UNISWAP_V3_POOL_ABI)
            token0 = contract.functions.token0().call()
            token1 = contract.functions.token1().call()
            slot0 = contract.functions.slot0().call()
            liquidity = contract.functions.liquidity().call()
            
            return {
                'address': checksum_address,
                'token0': token0,
                'token1': token1,
                'sqrtPriceX96': slot0[0],
                'tick': slot0[1],
                'liquidity': liquidity,
                'contract_type': contract_type
            }
        else:
            logger.warning(f"Unknown contract type for address {checksum_address}")
            return None
    except Exception as e:
        logger.error(f"Error fetching token info for {token_address}: {str(e)}")
        return None

def get_uniswap_v2_pairs(token_address):
    factory_contract = w3.eth.contract(address=UNISWAP_V2_FACTORY, abi=UNISWAP_V2_FACTORY_ABI)
    common_tokens = ['0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48', '0x6B175474E89094C44Da98b954EedeAC495271d0F']
    pairs = []
    for other_token in common_tokens:
        if other_token != token_address:
            pair_address = factory_contract.functions.getPair(token_address, other_token).call()
            if pair_address != '0x0000000000000000000000000000000000000000':
                pairs.append(pair_address)
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
                    pools.append(pool_address)
    return pools

def calculate_v2_price(reserve0, reserve1, decimals0, decimals1):
    if reserve0 == 0 or reserve1 == 0:
        return 0
    price = (Decimal(reserve1) / Decimal(10**decimals1)) / (Decimal(reserve0) / Decimal(10**decimals0))
    return float(price)

def calculate_v3_price(sqrt_price_x96, decimals0, decimals1):
    price = (Decimal(sqrt_price_x96) ** 2) / (2 ** 192)
    price *= Decimal(10) ** (decimals0 - decimals1)
    return float(price)

def validate_price(price):
    return 1e-12 < price < 1e12


async def update_redis_with_token_data(token_info):
    if token_info['contract_type'] == 'ERC20':
        token_key = f"token:{token_info['address']}"
        await redis_client.hset(token_key, mapping={
            'address': token_info['address'],
            'symbol': token_info['symbol'],
            'name': token_info['name'],
            'decimals': str(token_info['decimals']),
            'contract_type': token_info['contract_type']
        })
        
        for pair_address in token_info['v2_pairs']:
            pair_info = get_token_info(pair_address)
            if pair_info:
                await update_redis_with_token_data(pair_info)
        
        for pool_address in token_info['v3_pools']:
            pool_info = get_token_info(pool_address)
            if pool_info:
                await update_redis_with_token_data(pool_info)
    
    elif token_info['contract_type'] == 'UNISWAP_V2_PAIR':
        pair_key = f"uniswap_v2_pair:{token_info['address']}"
        price = calculate_v2_price(token_info['reserve0'], token_info['reserve1'], 
                                   w3.eth.contract(address=token_info['token0'], abi=ERC20_ABI).functions.decimals().call(),
                                   w3.eth.contract(address=token_info['token1'], abi=ERC20_ABI).functions.decimals().call())
        
        if validate_price(price):
            await redis_client.hset(pair_key, mapping={
                'address': token_info['address'],
                'token0': token_info['token0'],
                'token1': token_info['token1'],
                'reserve0': str(token_info['reserve0']),
                'reserve1': str(token_info['reserve1']),
                'price': str(price),
                'contract_type': token_info['contract_type'],
                'last_updated': str(int(time.time()))
            })
            logger.info(f"Updated V2 pair {token_info['address']} with price {price}")
        else:
            logger.warning(f"Invalid price calculated for V2 pair {token_info['address']}: {price}")
    
    elif token_info['contract_type'] == 'UNISWAP_V3_POOL':
        pool_key = f"uniswap_v3_pool:{token_info['address']}"
        price = calculate_v3_price(token_info['sqrtPriceX96'],
                                   w3.eth.contract(address=token_info['token0'], abi=ERC20_ABI).functions.decimals().call(),
                                   w3.eth.contract(address=token_info['token1'], abi=ERC20_ABI).functions.decimals().call())
        
        if validate_price(price):
            await redis_client.hset(pool_key, mapping={
                'address': token_info['address'],
                'token0': token_info['token0'],
                'token1': token_info['token1'],
                'sqrtPriceX96': str(token_info['sqrtPriceX96']),
                'tick': str(token_info['tick']),
                'liquidity': str(token_info['liquidity']),
                'price': str(price),
                'contract_type': token_info['contract_type'],
                'last_updated': str(int(time.time()))
            })
            logger.info(f"Updated V3 pool {token_info['address']} with price {price}")
        else:
            logger.warning(f"Invalid price calculated for V3 pool {token_info['address']}: {price}")

async def fetch_and_store_token_data(token_address):
    try:
        token_info = get_token_info(token_address)
        if token_info:
            await update_redis_with_token_data(token_info)
            logger.info(f"Stored data for token: {token_info.get('symbol', 'Unknown')} ({token_info['address']})")
        else:
            logger.warning(f"Failed to get token info for address {token_address}")
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

async def verify_redis_data():
    logger.info("Verifying Redis data...")
    
    # Check tokens
    tokens = await redis_client.keys("token:*")
    logger.info(f"Found {len(tokens)} tokens")
    for token_key in tokens[:5]:  # Log details of first 5 tokens
        token_data = await redis_client.hgetall(token_key)
        logger.info(f"Token data for {token_key}: {token_data}")
    
    # Check V2 pairs
    v2_pairs = await redis_client.keys("uniswap_v2_pair:*")
    logger.info(f"Found {len(v2_pairs)} V2 pairs")
    for pair_key in v2_pairs[:5]:  # Log details of first 5 pairs
        pair_data = await redis_client.hgetall(pair_key)
        logger.info(f"V2 pair data for {pair_key}: {pair_data}")
    
    # Check V3 pools
    v3_pools = await redis_client.keys("uniswap_v3_pool:*")
    logger.info(f"Found {len(v3_pools)} V3 pools")
    for pool_key in v3_pools[:5]:  # Log details of first 5 pools
        pool_data = await redis_client.hgetall(pool_key)
        logger.info(f"V3 pool data for {pool_key}: {pool_data}")
    
    # Check token pairs
    token_pairs = await redis_client.keys("token_pair:*")
    logger.info(f"Found {len(token_pairs)} token pairs")
    for pair_key in token_pairs[:5]:  # Log details of first 5 token pairs
        pair_data = await redis_client.hgetall(pair_key)
        logger.info(f"Token pair data for {pair_key}: {pair_data}")

async def update_prices():
    while True:
        v2_pairs = await redis_client.keys("uniswap_v2_pair:*")
        v3_pools = await redis_client.keys("uniswap_v3_pool:*")
        
        for pair_key in v2_pairs:
            pair_data = await redis_client.hgetall(pair_key)
            await fetch_and_store_token_data(pair_data['address'])
        
        for pool_key in v3_pools:
            pool_data = await redis_client.hgetall(pool_key)
            await fetch_and_store_token_data(pool_data['address'])
        
        logger.info("Updated all pool prices")
        await asyncio.sleep(300)  # Update every 5 minutes

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

        # Verify the initial data in Redis
        await verify_redis_data()

        logger.info("Initial token data insertion and pair generation complete")

        # Set up periodic price updates
        price_update_task = asyncio.create_task(update_prices())

        # Run the main loop
        while True:
            logger.info("Starting a new iteration of data updates")

            # Update token data and recalculate prices
            for token in all_tokens:
                if token['address']:
                    await fetch_and_store_token_data(token['address'])
                    await asyncio.sleep(0.2)

            # Verify the updated data in Redis
            await verify_redis_data()

            logger.info("Data update iteration complete")
            await asyncio.sleep(300)  # Wait for 5 minutes before the next iteration

    except asyncio.CancelledError:
        logger.info("Main task cancelled")
    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}")
        logger.exception("Exception details:")
    finally:
        logger.info("Closing connections and cleaning up")
        price_update_task.cancel()
        try:
            await price_update_task
        except asyncio.CancelledError:
            pass
        await redis_client.aclose()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Script terminated by user")
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")