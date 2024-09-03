import redis
from web3 import Web3
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Connect to Ethereum node (replace with your own endpoint)
w3 = Web3(Web3.HTTPProvider('http://localhost:8545'))

# ABIs
V2_POOL_ABI = [
    {"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"stateMutability":"view","type":"function"},
]

V3_POOL_ABI = [
    {"inputs":[],"name":"slot0","outputs":[{"internalType":"uint160","name":"sqrtPriceX96","type":"uint160"},{"internalType":"int24","name":"tick","type":"int24"},{"internalType":"uint16","name":"observationIndex","type":"uint16"},{"internalType":"uint16","name":"observationCardinality","type":"uint16"},{"internalType":"uint16","name":"observationCardinalityNext","type":"uint16"},{"internalType":"uint8","name":"feeProtocol","type":"uint8"},{"internalType":"bool","name":"unlocked","type":"bool"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"liquidity","outputs":[{"internalType":"uint128","name":"","type":"uint128"}],"stateMutability":"view","type":"function"},
]

def get_v2_data(pool_address):
    try:
        contract = w3.eth.contract(address=pool_address, abi=V2_POOL_ABI)
        reserves = contract.functions.getReserves().call()
        return {
            'reserve0': reserves[0],
            'reserve1': reserves[1],
            'price': reserves[1] / reserves[0] if reserves[0] != 0 else 0,
            'liquidity': (reserves[0] * reserves[1]) ** 0.5
        }
    except Exception as e:
        logging.error(f"Error fetching V2 data for {pool_address}: {str(e)}")
        return None

def get_v3_data(pool_address):
    try:
        contract = w3.eth.contract(address=pool_address, abi=V3_POOL_ABI)
        slot0 = contract.functions.slot0().call()
        liquidity = contract.functions.liquidity().call()
        sqrt_price_x96 = slot0[0]
        price = (sqrt_price_x96 / 2**96) ** 2
        return {
            'price': price,
            'liquidity': liquidity,
            'tick': slot0[1]
        }
    except Exception as e:
        logging.error(f"Error fetching V3 data for {pool_address}: {str(e)}")
        return None

def process_config(config_key):
    config_json = redis_client.get(config_key)
    config = json.loads(config_json)
    
    output = [f"\n{'=' * 50}", f"Config Pair: {config['name']}", f"{'=' * 50}"]
    
    # V2 Pool Data
    if config['v2_pool']:
        v2_data = get_v2_data(config['v2_pool'])
        if v2_data:
            output.extend([
                "Uniswap V2:",
                f"  Pool Address: {config['v2_pool']}",
                f"  Price: {v2_data['price']:.8f}",
                f"  Liquidity: {v2_data['liquidity']:.2f}"
            ])
        else:
            output.append("  Error fetching V2 data")
    else:
        output.append("No Uniswap V2 pool found.")
    
    # V3 Pool Data
    if config['v3_pools']:
        output.append("\nUniswap V3:")
        for fee_tier, pool_info in config['v3_pools'].items():
            v3_data = get_v3_data(pool_info['address'])
            if v3_data:
                output.extend([
                    f"  Fee Tier: {fee_tier}",
                    f"    Pool Address: {pool_info['address']}",
                    f"    Price: {v3_data['price']:.8f}",
                    f"    Liquidity: {v3_data['liquidity']}",
                    f"    Tick: {v3_data['tick']}"
                ])
            else:
                output.append(f"    Error fetching V3 data for {fee_tier}")
    else:
        output.append("No Uniswap V3 pools found.")
    
    output.extend(["\nRaw Config Data:", json.dumps(config, indent=2)])
    return '\n'.join(output)

def fetch_and_display_configs():
    config_keys = redis_client.keys('*_config')
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_key = {executor.submit(process_config, key): key for key in config_keys}
        for future in as_completed(future_to_key):
            print(future.result())
            time.sleep(0.1)  # Small delay to avoid rate limiting

if __name__ == "__main__":
    fetch_and_display_configs()