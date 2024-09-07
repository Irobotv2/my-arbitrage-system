from web3 import Web3
from web3.middleware import geth_poa_middleware
import redis
import json
import pandas as pd
import numpy as np

# Configuration
TENDERLY_URL = "http://localhost:8545"
web3 = Web3(Web3.HTTPProvider(TENDERLY_URL))
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

def get_pool_address(tokenA, tokenB, fee):
    try:
        pool_address = factory_contract.functions.getPool(tokenA, tokenB, fee).call()
        return pool_address if pool_address != '0x0000000000000000000000000000000000000000' else None
    except Exception as e:
        print(f"Error getting pool address: {e}")
        return None

def get_pool_liquidity(pool_address):
    try:
        pool_contract = web3.eth.contract(address=pool_address, abi=liquidity_abi)
        liquidity = pool_contract.functions.liquidity().call()
        return liquidity
    except Exception as e:
        print(f"Error getting pool liquidity: {e}")
        return None

def get_quote(tokenIn, tokenOut, amountIn, fee):
    try:
        amount_out = quoter_contract.functions.quoteExactInputSingle(
            tokenIn,
            tokenOut,
            fee,
            amountIn,
            0  # No price limit
        ).call()
        return amount_out
    except Exception as e:
        print(f"Error getting quote: {e}")
        return None

def get_quotes_for_all_tiers(tokenA, tokenB, amountIn):
    fee_tiers = [100, 500, 3000, 10000]  # 0.01%, 0.05%, 0.3%, 1% fee tiers
    quotes = {}
    for fee in fee_tiers:
        pool_address = get_pool_address(tokenA, tokenB, fee)
        if pool_address:
            liquidity = get_pool_liquidity(pool_address)
            quote = get_quote(tokenA, tokenB, amountIn, fee)
            quotes[fee] = {
                'pool_address': pool_address,
                'liquidity': liquidity,
                'quote': quote
            }
    return quotes

def fetch_all_configurations():
    configs = {}
    for key in redis_client.keys('*_config'):
        config_json = redis_client.get(key)
        config = json.loads(config_json)
        configs[key.decode('utf-8')] = config
    return configs

def test_liquidity_for_all_pairs():
    configurations = fetch_all_configurations()
    results = []

    for config_name, config in configurations.items():
        token0 = web3.to_checksum_address(config['token0']['address'])
        token1 = web3.to_checksum_address(config['token1']['address'])
        
        # Test with 1 ETH worth of token0
        amount_in = web3.to_wei(1, 'ether')
        
        quotes = get_quotes_for_all_tiers(token0, token1, amount_in)
        if quotes:
            token0_symbol = config['token0']['symbol']
            token1_symbol = config['token1']['symbol']
            
            print(f"\nQuotes for {token0_symbol}-{token1_symbol}:")
            for fee, data in quotes.items():
                if data['quote']:
                    print(f"Fee tier {fee/10000}%:")
                    print(f"  Pool address: {data['pool_address']}")
                    print(f"  Liquidity: {data['liquidity']}")
                    print(f"  1 ETH worth of {token0_symbol} can be exchanged for {data['quote'] / 1e18:.6f} {token1_symbol}")
                    
                    results.append({
                        "Pair": f"{token0_symbol}-{token1_symbol}",
                        "Fee Tier": f"{fee/10000}%",
                        "Pool Address": data['pool_address'],
                        "Liquidity": data['liquidity'],
                        "Input Amount": f"1 ETH worth of {token0_symbol}",
                        f"{token1_symbol} Received": data['quote'] / 1e18,  # Assuming 18 decimals, adjust if needed
                    })
        else:
            print(f"Failed to get quotes for {config_name}")

    # Create a DataFrame and save to CSV
    df = pd.DataFrame(results)
    df.to_csv('comprehensive_uniswap_v3_quotes.csv', index=False)
    print("\nResults saved to comprehensive_uniswap_v3_quotes.csv")

if __name__ == "__main__":
    test_liquidity_for_all_pairs()