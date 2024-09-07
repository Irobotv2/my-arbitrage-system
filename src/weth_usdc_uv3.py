import asyncio
import json
import websockets
from web3 import Web3
from web3.middleware import geth_poa_middleware
import redis
import concurrent.futures
import logging
import pandas as pd

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
HTTP_URL = "http://localhost:8545"  # Change this back to HTTP instead of WebSocket
web3 = Web3(Web3.HTTPProvider(HTTP_URL))
web3.middleware_onion.inject(geth_poa_middleware, layer=0)

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Uniswap V3 Factory and Quoter contract addresses (mainnet)
factory_address = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
quoter_address = "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6"

# ABIs
factory_abi = [
    {
        "inputs": [
            {"internalType": "address", "name": "token0", "type": "address"},
            {"internalType": "address", "name": "token1", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"}
        ],
        "name": "getPool",
        "outputs": [{"internalType": "address", "name": "pool", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]

quoter_abi = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenIn", "type": "address"},
            {"internalType": "address", "name": "tokenOut", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"}
        ],
        "name": "quoteExactInputSingle",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]

pool_abi = [
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

liquidity_abi = [
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [
            {"internalType": "uint128", "name": "", "type": "uint128"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

# Create contract objects
factory_contract = web3.eth.contract(address=factory_address, abi=factory_abi)
quoter_contract = web3.eth.contract(address=quoter_address, abi=quoter_abi)

def get_pool_data(token0, token1, fee):
    try:
        pool_address = factory_contract.functions.getPool(token0, token1, fee).call()
        if pool_address == '0x0000000000000000000000000000000000000000':
            return None
        
        pool_contract = web3.eth.contract(address=pool_address, abi=liquidity_abi)
        liquidity = pool_contract.functions.liquidity().call()
        
        return {
            'address': pool_address,
            'liquidity': liquidity
        }
    except Exception as e:
        logger.error(f"Error getting pool data: {e}")
        return None

def get_quote(token_in, token_out, amount_in, fee):
    try:
        quote = quoter_contract.functions.quoteExactInputSingle(
            token_in,
            token_out,
            fee,
            amount_in,
            0  # No price limit
        ).call()
        return quote
    except Exception as e:
        logger.error(f"Error getting quote for {token_in}-{token_out} with fee {fee}: {e}")
        return None

def update_pool_data():
    configurations = fetch_all_configurations()
    results = []
    for config_name, config in configurations.items():
        token0 = web3.to_checksum_address(config['token0']['address'])
        token1 = web3.to_checksum_address(config['token1']['address'])
        amount_in = web3.to_wei(1, 'ether')  # 1 ETH worth

        for fee in [100, 500, 3000, 10000]:  # 0.01%, 0.05%, 0.3%, 1% fee tiers
            pool_data = get_pool_data(token0, token1, fee)
            if pool_data:
                quote = get_quote(token0, token1, amount_in, fee)
                if quote:
                    redis_key = f"{config_name}:{fee}"
                    redis_client.hset(redis_key, mapping={
                        'pool_address': pool_data['address'],
                        'liquidity': pool_data['liquidity'],
                        'quote': quote
                    })
                    logger.info(f"Updated data for {config_name} with fee {fee}")
                    results.append({
                        "Pair": f"{config['token0']['symbol']}-{config['token1']['symbol']}",
                        "Fee Tier": f"{fee/10000}%",
                        "Pool Address": pool_data['address'],
                        "Liquidity": pool_data['liquidity'],
                        "Input Amount": f"1 ETH worth of {config['token0']['symbol']}",
                        f"{config['token1']['symbol']} Received": quote / 1e18,
                    })
    
    # Create a DataFrame and save to CSV
    df = pd.DataFrame(results)
    df.to_csv('comprehensive_uniswap_v3_quotes.csv', index=False)
    logger.info("Results saved to comprehensive_uniswap_v3_quotes.csv")

def fetch_all_configurations():
    configs = {}
    for key in redis_client.keys('*_config'):
        config_json = redis_client.get(key)
        config = json.loads(config_json)
        configs[key.decode('utf-8')] = config
    return configs

def main():
    logger.info("Starting arbitrage system")
    update_pool_data()
    logger.info("Finished updating pool data")

if __name__ == "__main__":
    main()