import redis
import json
from web3 import Web3
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Initialize Web3
w3 = Web3(Web3.HTTPProvider('http://localhost:8545'))

# Uniswap V3 Factory and V2 Factory addresses
UNISWAP_V3_FACTORY_ADDRESS = '0x1F98431c8aD98523631AE4a59f267346ea31F984'
UNISWAP_V2_FACTORY_ADDRESS = '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f'

# ABIs
UNISWAP_V3_FACTORY_ABI = [{"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"},{"internalType":"uint24","name":"fee","type":"uint24"}],"name":"getPool","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"}]
UNISWAP_V2_FACTORY_ABI = [{"constant":True,"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"}],"name":"getPair","outputs":[{"internalType":"address","name":"pair","type":"address"}],"payable":False,"stateMutability":"view","type":"function"}]

# Create contract instances
v3_factory_contract = w3.eth.contract(address=UNISWAP_V3_FACTORY_ADDRESS, abi=UNISWAP_V3_FACTORY_ABI)
v2_factory_contract = w3.eth.contract(address=UNISWAP_V2_FACTORY_ADDRESS, abi=UNISWAP_V2_FACTORY_ABI)

# Token addresses
USDC_ADDRESS = '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'
WETH_ADDRESS = '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'
DAI_ADDRESS = '0x6B175474E89094C44Da98b954EedeAC495271d0F'
WBTC_ADDRESS = '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599'

# Token pairs to add
TOKEN_PAIRS = [
    (USDC_ADDRESS, WETH_ADDRESS, 'USDC', 'WETH'),
    (WETH_ADDRESS, DAI_ADDRESS, 'WETH', 'DAI'),
    (DAI_ADDRESS, WBTC_ADDRESS, 'DAI', 'WBTC')
]

# Fee tiers for Uniswap V3
FEE_TIERS = [500, 3000, 10000]  # 0.05%, 0.3%, 1%

def get_v3_pool(token_a, token_b, fee):
    pool_address = v3_factory_contract.functions.getPool(token_a, token_b, fee).call()
    return pool_address if pool_address != '0x0000000000000000000000000000000000000000' else None

def get_v2_pool(token_a, token_b):
    pair_address = v2_factory_contract.functions.getPair(token_a, token_b).call()
    return pair_address if pair_address != '0x0000000000000000000000000000000000000000' else None

def add_config_to_redis(token_a, token_b, symbol_a, symbol_b):
    config = {
        'name': f'{symbol_a}-{symbol_b}',
        'token0': {'address': token_a, 'symbol': symbol_a},
        'token1': {'address': token_b, 'symbol': symbol_b},
        'v2_pool': get_v2_pool(token_a, token_b),
        'v3_pools': {}
    }

    for fee in FEE_TIERS:
        v3_pool = get_v3_pool(token_a, token_b, fee)
        if v3_pool:
            config['v3_pools'][f'{fee/10000:.2f}%'] = {'address': v3_pool, 'fee': fee}

    config_key = f"{symbol_a}_{symbol_b}_config"
    redis_client.set(config_key, json.dumps(config))
    logging.info(f"Added/Updated configuration for {symbol_a}-{symbol_b}")

def main():
    for token_a, token_b, symbol_a, symbol_b in TOKEN_PAIRS:
        add_config_to_redis(token_a, token_b, symbol_a, symbol_b)

if __name__ == "__main__":
    main()
    logging.info("Finished adding/updating configurations.")