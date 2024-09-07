import redis
from web3 import Web3
import json
import logging
import time
import os

# Initialize logging
logging.basicConfig(level=logging.INFO)

# Connect to Web3 providers
w3 = Web3(Web3.HTTPProvider('https://mainnet.infura.io/v3/0640f56f05a942d7a25cfeff50de344d'))

# Uniswap V3 Factory and V2 Factory addresses and ABI snippets
UNISWAP_V3_FACTORY_ADDRESS = '0x1F98431c8aD98523631AE4a59f267346ea31F984'
UNISWAP_V2_FACTORY_ADDRESS = '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f'

# ABIs
UNISWAP_V3_FACTORY_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"}
        ],
        "name": "getPool",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]

UNISWAP_V2_FACTORY_ABI = [
    {
        "constant": True,
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"}
        ],
        "name": "getPair",
        "outputs": [{"internalType": "address", "name": "pair", "type": "address"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    }
]

# ERC20 ABI for symbol() function
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    }
]

# Create contract instances
v3_factory_contract = w3.eth.contract(address=UNISWAP_V3_FACTORY_ADDRESS, abi=UNISWAP_V3_FACTORY_ABI)
v2_factory_contract = w3.eth.contract(address=UNISWAP_V2_FACTORY_ADDRESS, abi=UNISWAP_V2_FACTORY_ABI)

# Connect to Redis using environment variables
redis_host = os.getenv('REDIS_HOST', 'localhost')
redis_port = os.getenv('REDIS_PORT', 6379)
redis_db = os.getenv('REDIS_DB', 0)
redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_db)

# Updated list of token IDs
TOKEN_IDS = [
    '0xdAC17F958D2ee523a2206206994597C13D831ec7',  # USDT
    '0xB8c77482e45F1F44dE1745F52C74426C631bDD52',  # BNB
    '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48',  # USDC
    '0x628F76eAB0C1298F7a24d337bBbF1ef8A1Ea6A24',  # XRP
    '0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84',  # stETH
    '0x582d872A1B094FC48F5DE31D3B73F2D9bE47def1',  # TONCOIN
    '0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0',  # wstETH
    '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599',  # WBTC
    '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',  # WETH
    '0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE',  # SHIB
    '0x514910771AF9Ca656af840dff83E8264EcF986CA',  # LINK
    '0xC47ef9B19c3e29317a50F5fBE594EbA361dadA4A',  # EDLC
    '0x2AF5D2aD76741191D15Dfe7bF6aC92d4Bd912Ca3',  # LEO
    '0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0',  # MATIC
]

# Fee tiers for Uniswap V3
FEE_TIERS = [3000]

def generate_v3_pools(token_a, token_b):
    pools = {}
    for fee in FEE_TIERS:
        try:
            pool_address = v3_factory_contract.functions.getPool(token_a, token_b, fee).call()
            if pool_address != '0x0000000000000000000000000000000000000000':
                pools[f'{fee / 10000:.2%}'] = {'address': pool_address, 'fee': fee}
        except Exception as e:
            logging.exception(f"Error fetching V3 pool for {token_a} - {token_b} with fee {fee}: {str(e)}")
    return pools

def generate_v2_pool(token_a, token_b):
    try:
        pair_address = v2_factory_contract.functions.getPair(token_a, token_b).call()
        if pair_address != '0x0000000000000000000000000000000000000000':
            return pair_address
    except Exception as e:
        logging.exception(f"Error fetching V2 pool for {token_a} - {token_b}: {str(e)}")
    return None

def fetch_token_symbol(token_address):
    try:
        token_contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
        return token_contract.functions.symbol().call()
    except Exception as e:
        logging.exception(f"Error fetching symbol for token {token_address}: {str(e)}")
        return token_address[:6]  # Use first 6 characters as fallback

def create_and_store_configs():
    for i, token_a in enumerate(TOKEN_IDS):
        for token_b in TOKEN_IDS[i + 1:]:
            logging.info(f"Processing pair: {token_a} - {token_b}")
            
            v2_pool_address = generate_v2_pool(token_a, token_b)
            v3_pools = generate_v3_pools(token_a, token_b)
            
            if not v2_pool_address and not v3_pools:
                logging.info(f"No pools found for {token_a} - {token_b}")
                continue
            
            token_a_symbol = fetch_token_symbol(token_a)
            token_b_symbol = fetch_token_symbol(token_b)
            
            config = {
                'name': f'{token_a_symbol}-{token_b_symbol}',
                'v2_pool': v2_pool_address,
                'v3_pools': v3_pools,
                'token0': {'address': token_a, 'symbol': token_a_symbol},
                'token1': {'address': token_b, 'symbol': token_b_symbol}
            }
            
            config_key = f"{token_a_symbol}_{token_b_symbol}_config"
            redis_client.set(config_key, json.dumps(config))
            logging.info(f"Stored config for {token_a_symbol}-{token_b_symbol}")
            
            # Add a small delay to avoid rate limiting
            time.sleep(0.5)

if __name__ == "__main__":
    create_and_store_configs()
    logging.info("Finished processing all pairs.")
