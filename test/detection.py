import json
import logging
from decimal import Decimal
from web3 import Web3
from web3.middleware import geth_poa_middleware
import redis

# Initialize logging
logging.basicConfig(level=logging.INFO)

# Setup Web3 connection
provider_url = 'http://localhost:8545'  # Update with your local provider
w3 = Web3(Web3.HTTPProvider(provider_url, request_kwargs={'timeout': 30}))
w3.middleware_onion.inject(geth_poa_middleware, layer=0)

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# ABI definitions (trimmed for brevity)
V2_POOL_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"internalType": "uint112", "name": "_reserve0", "type": "uint112"},
            {"internalType": "uint112", "name": "_reserve1", "type": "uint112"},
            {"internalType": "uint32", "name": "_blockTimestampLast", "type": "uint32"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]
V3_POOL_ABI = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
            {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
            {"internalType": "bool", "name": "unlocked", "type": "bool"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function"
    }
]
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    }
]

def get_token_decimals(token_address):
    """Get the number of decimals for a token."""
    if not token_address:
        logging.warning("Token address is missing.")
        return None
    token_contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
    return token_contract.functions.decimals().call()

def check_v2_pool_exists(pool_address):
    """Check if a V2 pool exists and has non-zero reserves."""
    if not pool_address:
        logging.warning("V2 pool address is missing.")
        return False
    try:
        v2_pool_contract = w3.eth.contract(address=pool_address, abi=V2_POOL_ABI)
        reserves = v2_pool_contract.functions.getReserves().call()
        if reserves[0] == 0 or reserves[1] == 0:
            logging.warning(f"V2 Pool {pool_address} has zero reserves. Skipping.")
            return False
        logging.info(f"V2 Pool {pool_address} exists with reserves: {reserves}")
        return True
    except Exception as e:
        logging.error(f"Error checking V2 pool {pool_address}: {str(e)}")
        return False

def check_v3_pool_liquidity(pool_address):
    """Check if a V3 pool has non-zero liquidity."""
    if not pool_address:
        logging.warning("V3 pool address is missing.")
        return False
    try:
        v3_pool_contract = w3.eth.contract(address=pool_address, abi=V3_POOL_ABI)
        liquidity = v3_pool_contract.functions.liquidity().call()
        if liquidity == 0:
            logging.warning(f"V3 Pool {pool_address} has zero liquidity. Skipping.")
            return False
        logging.info(f"V3 Pool {pool_address} has liquidity: {liquidity}")
        return True
    except Exception as e:
        logging.error(f"Error checking V3 pool liquidity {pool_address}: {str(e)}")
        return False

def load_configurations_from_redis():
    """Load pool configurations from Redis."""
    configs = {}
    try:
        for key in redis_client.keys('*_config'):  # Adjust the pattern to match your keys
            config_json = redis_client.get(key)
            config = json.loads(config_json)
            configs[key.decode('utf-8')] = config
        logging.info("Configurations loaded successfully from Redis.")
    except Exception as e:
        logging.error(f"Error loading configurations from Redis: {str(e)}")
    return configs

def get_price_v2(pool_contract, token0_decimals, token1_decimals):
    """Calculate the price for a V2 pool."""
    try:
        reserves = pool_contract.functions.getReserves().call()
        reserve0 = Decimal(reserves[0])
        reserve1 = Decimal(reserves[1])
        normalized_reserve0 = reserve0 / Decimal(10 ** token0_decimals)
        normalized_reserve1 = reserve1 / Decimal(10 ** token1_decimals)
        price = normalized_reserve1 / normalized_reserve0
        logging.info(f"V2 Price Calculation: reserve0={reserve0}, reserve1={reserve1}, price={price}")
        if price <= 0:
            logging.warning(f"V2 Price is zero or negative: {price}")
        return float(price)
    except Exception as e:
        logging.error(f"Error calculating V2 price: {str(e)}")
        return None

def get_price_v3(pool_contract, token0_decimals, token1_decimals):
    """Calculate the price for a V3 pool."""
    try:
        slot0_data = pool_contract.functions.slot0().call()
        sqrt_price_x96 = slot0_data[0]
        return sqrt_price_x96_to_price(sqrt_price_x96, token0_decimals, token1_decimals)
    except Exception as e:
        logging.error(f"Error getting V3 slot0 data: {str(e)}")
        return None

def sqrt_price_x96_to_price(sqrt_price_x96, token0_decimals, token1_decimals):
    """Convert sqrtPriceX96 to a normal price."""
    try:
        sqrt_price = Decimal(sqrt_price_x96) / Decimal(2 ** 96)
        price = sqrt_price ** 2
        decimal_adjustment = Decimal(10 ** (token1_decimals - token0_decimals))
        adjusted_price = price * decimal_adjustment
        logging.info(f"V3 Price Calculation: sqrt_price_x96={sqrt_price_x96}, adjusted_price={adjusted_price}")
        if adjusted_price <= 0:
            logging.warning(f"V3 Price is zero or negative: {adjusted_price}")
        return float(adjusted_price)
    except Exception as e:
        logging.error(f"Error calculating V3 price: {str(e)}")
        return None

def analyze_configurations(configs):
    """Analyze the loaded pool configurations."""
    for config_name, config in configs.items():
        logging.info(f"Analyzing configuration: {config_name}")
        token0_address = config['token0'].get('address')
        token1_address = config['token1'].get('address')
        token0_decimals = get_token_decimals(token0_address)
        token1_decimals = get_token_decimals(token1_address)

        # Check V2 pool
        if config.get('v2_pool') and check_v2_pool_exists(config['v2_pool']):
            v2_pool_contract = w3.eth.contract(address=config['v2_pool'], abi=V2_POOL_ABI)
            price_v2 = get_price_v2(v2_pool_contract, token0_decimals, token1_decimals)
            logging.info(f"V2 Price for {config_name}: {price_v2}")
        else:
            logging.warning(f"V2 pool {config.get('v2_pool')} is invalid or does not exist.")

        # Check V3 pools
        for fee_tier, pool_info in config.get('v3_pools', {}).items():
            if check_v3_pool_liquidity(pool_info['address']):
                v3_pool_contract = w3.eth.contract(address=pool_info['address'], abi=V3_POOL_ABI)
                price_v3 = get_price_v3(v3_pool_contract, token0_decimals, token1_decimals)
                logging.info(f"V3 Price for {config_name} (fee {fee_tier}): {price_v3}")
            else:
                logging.warning(f"V3 pool {pool_info['address']} for fee tier {fee_tier} has insufficient liquidity.")

if __name__ == "__main__":
    logging.info("Starting analysis...")
    configs = load_configurations_from_redis()
    if configs:
        analyze_configurations(configs)
    else:
        logging.error("No valid configurations found in Redis.")
