import redis
from web3 import Web3
import json
import logging
import time

# Initialize logging
logging.basicConfig(level=logging.INFO)

# Connect to Web3 providers
w3 = Web3(Web3.HTTPProvider('https://sepolia.infura.io/v3/0640f56f05a942d7a25cfeff50de344d'))

# Convert factory addresses to checksum format
UNISWAP_V3_FACTORY_ADDRESS = Web3.to_checksum_address('0x0227628f3F023bb0B980b67D528571c95c6DaC1c')
UNISWAP_V2_FACTORY_ADDRESS = Web3.to_checksum_address('0x7E0987E5b3a30e3f2828572bB659A548460a3003')  # Updated V2 factory address

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

# Create contract instances with corrected checksum addresses
v3_factory_contract = w3.eth.contract(address=UNISWAP_V3_FACTORY_ADDRESS, abi=UNISWAP_V3_FACTORY_ABI)
v2_factory_contract = w3.eth.contract(address=UNISWAP_V2_FACTORY_ADDRESS, abi=UNISWAP_V2_FACTORY_ABI)

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Updated list of token IDs for Sepolia
TOKEN_IDS = [
    Web3.to_checksum_address('0x2C032Aa43D119D7bf4Adc42583F1f94f3bf3023a'),  # USDC on Sepolia
    Web3.to_checksum_address('0x5f207d42f869fd1c71d7f0f81a2a67fc20ff7323'),  # WETH on Sepolia
    Web3.to_checksum_address('0xBeA8F9D2f2bDcA1dDEdA7147c72Fc04a810e6d82'),  # DAI on Sepolia
    Web3.to_checksum_address('0xD5E5fDBC6c21697A4e269C6c1F77E0d8c1f3e9Ce'),  # WBTC on Sepolia
    Web3.to_checksum_address('0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'),  # LINK on Sepolia
]

# Fee tiers for Uniswap V3
FEE_TIERS = [100, 500, 3000, 10000]

def generate_v3_pools(token_a, token_b):
    pools = {}
    for fee in FEE_TIERS:
        try:
            pool_address = v3_factory_contract.functions.getPool(token_a, token_b, fee).call()
            if pool_address != '0x0000000000000000000000000000000000000000':
                pools[f'{fee / 10000:.2%}'] = {'address': pool_address, 'fee': fee}
        except Exception as e:
            logging.error(f"Error fetching V3 pool for {token_a} - {token_b} with fee {fee}: {str(e)}")
    return pools

def generate_v2_pool(token_a, token_b):
    try:
        pair_address = v2_factory_contract.functions.getPair(token_a, token_b).call()
        if pair_address != '0x0000000000000000000000000000000000000000':
            return pair_address
    except Exception as e:
        logging.error(f"Error fetching V2 pool for {token_a} - {token_b}: {str(e)}")
    return None

def fetch_token_symbol(token_address):
    try:
        token_contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
        return token_contract.functions.symbol().call()
    except Exception as e:
        logging.error(f"Error fetching symbol for token {token_address}: {str(e)}")
        return token_address[:6]  # Use first 6 characters as fallback

def create_and_store_configs():
    for i, token_a in enumerate(TOKEN_IDS):
        for token_b in TOKEN_IDS[i + 1:]:
            logging.info(f"Processing pair: {token_a} - {token_b}")
            
            # Ensure token addresses are in checksum format
            token_a = Web3.to_checksum_address(token_a)
            token_b = Web3.to_checksum_address(token_b)

            v2_pool_address = generate_v2_pool(token_a, token_b)
            v3_pools = generate_v3_pools(token_a, token_b)
            
            if not v2_pool_address and not v3_pools:
                logging.info(f"No pools found for {token_a} - {token_b}")
                continue
            
            token_a_symbol = fetch_token_symbol(token_a)
            token_b_symbol = fetch_token_symbol(token_b)
            
            config = {
                'network': 'Sepolia',  # Explicitly mention Sepolia testnet
                'name': f'{token_a_symbol}-{token_b_symbol}',
                'v2_pool': v2_pool_address,
                'v3_pools': v3_pools,
                'token0': {'address': token_a, 'symbol': token_a_symbol},
                'token1': {'address': token_b, 'symbol': token_b_symbol}
            }
            
            config_key = f"sepolia_{token_a_symbol}_{token_b_symbol}_config"
            redis_client.set(config_key, json.dumps(config))
            logging.info(f"Stored Sepolia config for {token_a_symbol}-{token_b_symbol}")
            
            # Add a small delay to avoid rate limiting
            time.sleep(0.5)

if __name__ == "__main__":
    create_and_store_configs()
    logging.info("Finished processing all pairs.")
