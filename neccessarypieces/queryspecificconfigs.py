import redis
import json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Configurations to query
CONFIGS_TO_QUERY = [
    "USDC_WETH_config",
    "WETH_DAI_config",
    "DAI_WBTC_config"
]

def format_pool_info(pool_info):
    if isinstance(pool_info, dict):
        return {
            'address': pool_info['address'],
            'fee': f"{pool_info['fee']/10000:.2f}%"
        }
    return pool_info

def query_and_display_config(config_key):
    config_json = redis_client.get(config_key)
    if config_json:
        config = json.loads(config_json)
        logging.info(f"\nConfiguration for {config['name']}:")
        logging.info(f"Token0: {config['token0']['symbol']} ({config['token0']['address']})")
        logging.info(f"Token1: {config['token1']['symbol']} ({config['token1']['address']})")
        
        if config.get('v2_pool'):
            logging.info(f"Uniswap V2 Pool: {config['v2_pool']}")
        else:
            logging.info("No Uniswap V2 Pool found")
        
        if config.get('v3_pools'):
            logging.info("Uniswap V3 Pools:")
            for fee_tier, pool_info in config['v3_pools'].items():
                formatted_pool = format_pool_info(pool_info)
                logging.info(f"  {fee_tier}: {formatted_pool}")
        else:
            logging.info("No Uniswap V3 Pools found")
    else:
        logging.warning(f"No configuration found for {config_key}")

def main():
    for config_key in CONFIGS_TO_QUERY:
        query_and_display_config(config_key)

if __name__ == "__main__":
    main()