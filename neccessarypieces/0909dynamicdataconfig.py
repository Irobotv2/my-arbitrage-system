import redis
import json
from web3 import Web3
import logging
from itertools import combinations

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

# List of tokens with address and symbol
tokens = [
    {"symbol": "USDT", "address": "0xdAC17F958D2ee523a2206206994597C13D831ec7", "decimals": 6},
    {"symbol": "BNB", "address": "0xB8c77482e45F1F44dE1745F52C74426C631bDD52", "decimals": 18},
    {"symbol": "USDC", "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "decimals": 6},
    {"symbol": "XRP", "address": "0x628F76eAB0C1298F7a24d337bBbF1ef8A1Ea6A24", "decimals": 6},
    {"symbol": "stETH", "address": "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84", "decimals": 18},
    {"symbol": "TONCOIN", "address": "0x582d872A1B094FC48F5DE31D3B73F2D9bE47def1", "decimals": 9},
    {"symbol": "wstETH", "address": "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0", "decimals": 18},
    {"symbol": "WBTC", "address": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", "decimals": 8},
    {"symbol": "WETH", "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "decimals": 18},
    {"symbol": "SHIB", "address": "0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE", "decimals": 18},
    {"symbol": "LINK", "address": "0x514910771AF9Ca656af840dff83E8264EcF986CA", "decimals": 18},
    {"symbol": "EDLC", "address": "0xC47ef9B19c3e29317a50F5fBE594EbA361dadA4A", "decimals": 6},
    {"symbol": "LEO", "address": "0x2AF5D2aD76741191D15Dfe7bF6aC92d4Bd912Ca3", "decimals": 18},
    {"symbol": "MATIC", "address": "0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0", "decimals": 18},
    {"symbol": "DAI", "address": "0x6B175474E89094C44Da98b954EedeAC495271d0F", "decimals": 18},
    {"symbol": "AAVE", "address": "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9", "decimals": 18},
    {"symbol": "stkAAVE", "address": "0x4da27a545c0c5B758a6BA100e3a049001de870f5", "decimals": 18},
    {"symbol": "PEOPLE", "address": "0x7A58c0Be72BE218B41C608b7Fe7C5bB630736C71", "decimals": 18},
    {"symbol": "FET", "address": "0xaea46A60368A7bD060eec7DF8CBa43b7EF41Ad85", "decimals": 18},
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
    # Generate all unique token pairs
    token_pairs = combinations(tokens, 2)

    for token1, token2 in token_pairs:
        add_config_to_redis(token1['address'], token2['address'], token1['symbol'], token2['symbol'])

if __name__ == "__main__":
    main()
    logging.info("Finished adding/updating configurations.")
