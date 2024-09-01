import redis
from web3 import Web3
import json
import logging
from logging.handlers import RotatingFileHandler

# Initialize logging
def setup_logger(name, log_file, level=logging.INFO):
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger

main_logger = setup_logger('config_validator', 'config_validation.log')

# Setup Web3 connection
provider_url = 'http://localhost:8545'  # Replace with your Ethereum node URL
w3 = Web3(Web3.HTTPProvider(provider_url))

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# ABIs (Add only the necessary parts)
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    }
]

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
    }
]

def load_configurations_from_redis():
    configs = {}
    for key in redis_client.keys('*_config'):
        config_json = redis_client.get(key)
        config = json.loads(config_json)
        configs[key.decode('utf-8')] = config
    return configs

def get_token_decimals(token_address):
    token_contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
    return token_contract.functions.decimals().call()

def get_price_v2(pool_contract, token0_decimals, token1_decimals):
    reserves = pool_contract.functions.getReserves().call()
    reserve0 = reserves[0]
    reserve1 = reserves[1]
    
    normalized_reserve0 = reserve0 / (10 ** token0_decimals)
    normalized_reserve1 = reserve1 / (10 ** token1_decimals)

    return normalized_reserve1 / normalized_reserve0

def get_price_v3(pool_contract, token0_decimals, token1_decimals):
    slot0_data = pool_contract.functions.slot0().call()
    sqrt_price_x96 = slot0_data[0]
    price = (sqrt_price_x96 ** 2) / (2 ** 192)
    decimal_adjustment = 10 ** (token1_decimals - token0_decimals)
    return price * decimal_adjustment

def validate_configurations():
    configurations = load_configurations_from_redis()
    main_logger.info(f"Loaded {len(configurations)} configurations from Redis")

    for config_name, config in configurations.items():
        main_logger.info(f"Validating configuration: {config_name}")

        # Check if all required fields are present
        required_fields = ['name', 'v2_pool', 'v3_pools', 'token0', 'token1']
        if not all(field in config for field in required_fields):
            main_logger.error(f"Configuration {config_name} is missing required fields")
            continue

        # Verify token addresses
        token0_address = config['token0']['address']
        token1_address = config['token1']['address']
        if not (w3.is_address(token0_address) and w3.is_address(token1_address)):
            main_logger.error(f"Invalid token addresses in configuration {config_name}")
            continue

        # Verify V2 pool address
        v2_pool_address = config['v2_pool']
        if not w3.is_address(v2_pool_address):
            main_logger.error(f"Invalid V2 pool address in configuration {config_name}")
            continue

        # Verify V3 pool addresses
        for fee_tier, pool_info in config['v3_pools'].items():
            if not w3.is_address(pool_info['address']):
                main_logger.error(f"Invalid V3 pool address for fee tier {fee_tier} in configuration {config_name}")
                continue

        # Fetch token decimals
        try:
            token0_decimals = get_token_decimals(token0_address)
            token1_decimals = get_token_decimals(token1_address)
            main_logger.info(f"{config_name} - Token0 decimals: {token0_decimals}, Token1 decimals: {token1_decimals}")
        except Exception as e:
            main_logger.error(f"Error fetching token decimals for configuration {config_name}: {str(e)}")
            continue

        # Fetch V2 price
        try:
            v2_pool_contract = w3.eth.contract(address=v2_pool_address, abi=V2_POOL_ABI)
            price_v2 = get_price_v2(v2_pool_contract, token0_decimals, token1_decimals)
            main_logger.info(f"{config_name} - V2 Price: {price_v2}")
        except Exception as e:
            main_logger.error(f"Error fetching V2 price for configuration {config_name}: {str(e)}")
            price_v2 = None

        # Fetch V3 prices
        for fee_tier, pool_info in config['v3_pools'].items():
            try:
                v3_pool_contract = w3.eth.contract(address=pool_info['address'], abi=V3_POOL_ABI)
                price_v3 = get_price_v3(v3_pool_contract, token0_decimals, token1_decimals)
                main_logger.info(f"{config_name} - V3 Price ({fee_tier}): {price_v3}")

                # Check for potential arbitrage opportunity
                if price_v2 is not None:
                    price_diff = abs(price_v3 - price_v2) / min(price_v2, price_v3)
                    main_logger.info(f"{config_name} - Price difference: {price_diff:.2%}")
                    if price_diff > 0.005:  # 0.5% threshold
                        main_logger.info(f"Potential arbitrage opportunity for {config_name} ({fee_tier})")

            except Exception as e:
                main_logger.error(f"Error fetching V3 price for configuration {config_name}, fee tier {fee_tier}: {str(e)}")

        main_logger.info(f"Finished validating configuration: {config_name}\n")

if __name__ == "__main__":
    main_logger.info("Starting configuration validation...")
    validate_configurations()
    main_logger.info("Configuration validation complete.")