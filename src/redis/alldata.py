import requests
import redis
import time
from web3 import Web3
import json
import logging
from ratelimit import limits, sleep_and_retry
from itertools import cycle

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='uniswap_data_update.log', filemode='a')
logger = logging.getLogger(__name__)

# Add console handler
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

INFURA_PROJECT_ID = "0640f56f05a942d7a25cfeff50de344d"
UNISWAP_V2_FACTORY = "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"
UNISWAP_V3_FACTORY = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_DB = 0

# Initialize Web3 and Redis
w3 = Web3(Web3.WebsocketProvider(f'wss://mainnet.infura.io/ws/v3/{INFURA_PROJECT_ID}'))
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)

# Add Uniswap V2 Pair ABI (for fetching reserves)
UNISWAP_V2_PAIR_ABI = json.loads('[{"constant":true,"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"payable":false,"stateMutability":"view","type":"function"}]')

# Add Uniswap V3 Pool ABI (for fetching liquidity, tick, and sqrtPrice)
UNISWAP_V3_POOL_ABI = json.loads('[{"inputs":[],"name":"liquidity","outputs":[{"internalType":"uint128","name":"","type":"uint128"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"slot0","outputs":[{"internalType":"uint160","name":"sqrtPriceX96","type":"uint160"},{"internalType":"int24","name":"tick","type":"int24"},{"internalType":"uint16","name":"observationIndex","type":"uint16"},{"internalType":"uint16","name":"observationCardinality","type":"uint16"},{"internalType":"uint16","name":"observationCardinalityNext","type":"uint16"},{"internalType":"uint8","name":"feeProtocol","type":"uint8"},{"internalType":"bool","name":"unlocked","type":"bool"}],"stateMutability":"view","type":"function"}]')

def get_next_api_key():
    return next(api_key_cycle)

@sleep_and_retry
@limits(calls=5, period=1)  # 5 calls per second across all keys
def call_etherscan_api(url):
    for _ in range(3):  # Try up to 3 times
        api_key = get_next_api_key()
        full_url = f"{url}&apikey={api_key}"
        response = requests.get(full_url)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 502:
            logger.warning(f"Received 502 error. Retrying with a different API key...")
            time.sleep(1)  # Wait a bit before retrying
        else:
            raise Exception(f"API request failed with status code {response.status_code}")
    raise Exception("Failed to get a successful response after 3 attempts")

def fetch_logs(url, topic0):
    all_logs = []
    from_block = 0
    to_block = 'latest'
    
    while True:
        current_url = f"{url}&fromBlock={from_block}&toBlock={to_block}"
        try:
            data = call_etherscan_api(current_url)
            
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
            time.sleep(0.1)  # Small delay between requests
        except Exception as e:
            logger.error(f"Error fetching logs: {e}")
            time.sleep(1)  # Wait a bit longer on error
    
    return all_logs

def fetch_uniswap_v2_pairs():
    url = f"https://api.etherscan.io/api?module=logs&action=getLogs&address={UNISWAP_V2_FACTORY}&topic0=0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9"
    logs = fetch_logs(url, "0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9")

    pairs = []
    for log in logs:
        pair_address = '0x' + log['data'][26:66]
        token0 = '0x' + log['topics'][1][26:]
        token1 = '0x' + log['topics'][2][26:]
        pairs.append({
            'pair_address': Web3.to_checksum_address(pair_address),
            'token0': Web3.to_checksum_address(token0),
            'token1': Web3.to_checksum_address(token1)
        })

    logger.info(f"Fetched {len(pairs)} Uniswap V2 pairs")
    return pairs

def fetch_uniswap_v3_pools():
    url = f"https://api.etherscan.io/api?module=logs&action=getLogs&address={UNISWAP_V3_FACTORY}&topic0=0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118"
    logs = fetch_logs(url, "0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118")

    pools = []
    for log in logs:
        pool_address = '0x' + log['data'][26:66]
        token0 = '0x' + log['topics'][1][26:]
        token1 = '0x' + log['topics'][2][26:]
        fee = int(log['topics'][3], 16)
        pools.append({
            'pool_address': Web3.to_checksum_address(pool_address),
            'token0': Web3.to_checksum_address(token0),
            'token1': Web3.to_checksum_address(token1),
            'fee': fee
        })

    logger.info(f"Fetched {len(pools)} Uniswap V3 pools")
    return pools

@sleep_and_retry
@limits(calls=10, period=1)
def validate_address(address):
    url = f"https://api.etherscan.io/api?module=contract&action=getabi&address={address}"
    data = call_etherscan_api(url)
    return data['status'] == '1' and data['message'] == 'OK'

def fetch_v2_pair_data(pair_address):
    logger.info(f"Fetching data for V2 pair: {pair_address}")
    pair_contract = w3.eth.contract(address=pair_address, abi=UNISWAP_V2_PAIR_ABI)
    reserves = pair_contract.functions.getReserves().call()
    data = {
        'reserve0': str(reserves[0]),
        'reserve1': str(reserves[1]),
        'fee': '0.003',  # Store as string for exact Decimal comparison
        'last_updated': str(int(time.time()))
    }
    logger.info(f"V2 pair data: {data}")
    return data

def fetch_v3_pool_data(pool_address):
    logger.info(f"Fetching data for V3 pool: {pool_address}")
    pool_contract = w3.eth.contract(address=pool_address, abi=UNISWAP_V3_POOL_ABI)
    liquidity = pool_contract.functions.liquidity().call()
    slot0 = pool_contract.functions.slot0().call()
    sqrt_price_x96 = slot0[0]
    tick = slot0[1]
    
    # Calculate price from sqrtPriceX96
    price = (sqrt_price_x96 / (2**96)) ** 2
    
    data = {
        'liquidity': str(liquidity),
        'current_tick': str(tick),
        'sqrt_price': str(sqrt_price_x96),
        'calculated_price': str(price),
        'last_updated': str(int(time.time())),
        'volume_24h_usd': '0'  # Store as string for consistency
    }
    logger.info(f"V3 pool data: {data}")
    return data

def update_redis_with_validated_data(v2_pairs, v3_pools):
    logger.info("Starting to update Redis with validated data")
    v2_count = 0
    v3_count = 0
    for pair in v2_pairs:
        if validate_address(pair['pair_address']):
            key = f"uniswap_v2_pairs:{pair['pair_address']}"
            if not redis_client.exists(key):
                data = {
                    'token0_address': pair['token0'],
                    'token1_address': pair['token1'],
                    'pair_address': pair['pair_address']
                }
                # Fetch additional data
                additional_data = fetch_v2_pair_data(pair['pair_address'])
                data.update(additional_data)
                redis_client.hset(key, mapping=data)
                v2_count += 1
                logger.info(f"Updated V2 pair: {pair['pair_address']}")
            else:
                logger.info(f"V2 pair already exists in Redis: {pair['pair_address']}")

    for pool in v3_pools:
        if validate_address(pool['pool_address']):
            key = f"uniswap_v3_pools:{pool['pool_address']}"
            if not redis_client.exists(key):
                data = {
                    'token0_address': pool['token0'],
                    'token1_address': pool['token1'],
                    'pool_address': pool['pool_address'],
                    'fee_tier': str(pool['fee'])
                }
                # Fetch additional data
                additional_data = fetch_v3_pool_data(pool['pool_address'])
                data.update(additional_data)
                redis_client.hset(key, mapping=data)
                v3_count += 1
                logger.info(f"Updated V3 pool: {pool['pool_address']}")
            else:
                logger.info(f"V3 pool already exists in Redis: {pool['pool_address']}")

    logger.info(f"Updated {v2_count} V2 pairs and {v3_count} V3 pools in Redis")

def handle_new_v2_pair(event):
    pair_address = event['args']['pair']
    token0 = event['args']['token0']
    token1 = event['args']['token1']
    
    if validate_address(pair_address):
        key = f"uniswap_v2_pairs:{pair_address}"
        if not redis_client.exists(key):
            data = {
                'token0_address': token0,
                'token1_address': token1,
                'pair_address': pair_address
            }
            additional_data = fetch_v2_pair_data(pair_address)
            data.update(additional_data)
            redis_client.hset(key, mapping=data)
            logger.info(f"Added new V2 pair: {pair_address}")

def handle_new_v3_pool(event):
    pool_address = event['args']['pool']
    token0 = event['args']['token0']
    token1 = event['args']['token1']
    fee = event['args']['fee']
    
    if validate_address(pool_address):
        key = f"uniswap_v3_pools:{pool_address}"
        if not redis_client.exists(key):
            data = {
                'token0_address': token0,
                'token1_address': token1,
                'pool_address': pool_address,
                'fee_tier': str(fee)
            }
            additional_data = fetch_v3_pool_data(pool_address)
            data.update(additional_data)
            redis_client.hset(key, mapping=data)
            logger.info(f"Added new V3 pool: {pool_address}")

def main():
    logger.info("Starting Uniswap data update process")
    # Fetch initial data
    v2_pairs = fetch_uniswap_v2_pairs()
    v3_pools = fetch_uniswap_v3_pools()

    # Update Redis with initial data
    update_redis_with_validated_data(v2_pairs, v3_pools)

    # Set up event filters
    v2_factory_abi = json.loads('[{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"token0","type":"address"},{"indexed":true,"internalType":"address","name":"token1","type":"address"},{"indexed":false,"internalType":"address","name":"pair","type":"address"},{"indexed":false,"internalType":"uint256","name":"","type":"uint256"}],"name":"PairCreated","type":"event"}]')
    v3_factory_abi = json.loads('[{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"token0","type":"address"},{"indexed":true,"internalType":"address","name":"token1","type":"address"},{"indexed":true,"internalType":"uint24","name":"fee","type":"uint24"},{"indexed":false,"internalType":"int24","name":"tickSpacing","type":"int24"},{"indexed":false,"internalType":"address","name":"pool","type":"address"}],"name":"PoolCreated","type":"event"}]')

    v2_factory_contract = w3.eth.contract(address=UNISWAP_V2_FACTORY, abi=v2_factory_abi)
    v3_factory_contract = w3.eth.contract(address=UNISWAP_V3_FACTORY, abi=v3_factory_abi)

    v2_event_filter = v2_factory_contract.events.PairCreated.create_filter(fromBlock='latest')
    v3_event_filter = v3_factory_contract.events.PoolCreated.create_filter(fromBlock='latest')

    logger.info("Starting main loop to listen for new pairs/pools")
    # Main loop
    while True:
        try:
            for event in v2_event_filter.get_new_entries():
                handle_new_v2_pair(event)

            for event in v3_event_filter.get_new_entries():
                handle_new_v3_pool(event)

            # Sleep to avoid hammering the node
            time.sleep(10)
        except Exception as e:
            logger.error(f"An error occurred in the main loop: {e}")
            time.sleep(60)  # Wait a bit longer before retrying

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Script terminated by user")
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
    finally:
        logger.info("Closing connections")
        w3.provider.close()
        redis_client.close()
