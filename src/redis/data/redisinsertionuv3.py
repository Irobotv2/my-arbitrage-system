import redis
from web3 import Web3
from web3.exceptions import ContractLogicError
import json
import math

# Connect to Ethereum network (replace with your provider URL)
w3 = Web3(Web3.HTTPProvider('https://mainnet.infura.io/v3/0640f56f05a942d7a25cfeff50de344d'))

# Uniswap V3 Factory contract address
FACTORY_ADDRESS = '0x1F98431c8aD98523631AE4a59f267346ea31F984'

# Uniswap V3 Quoter contract address
QUOTER_ADDRESS = '0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6'

# Uniswap V3 Factory ABI (only the getPool function)
FACTORY_ABI = [
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

# Uniswap V3 Pool ABI (only the slot0 function)
POOL_ABI = [
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

# Uniswap V3 Quoter ABI (only the quoteExactInputSingle function)
QUOTER_ABI = [
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
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

# Create contract instances
factory_contract = w3.eth.contract(address=FACTORY_ADDRESS, abi=FACTORY_ABI)
quoter_contract = w3.eth.contract(address=QUOTER_ADDRESS, abi=QUOTER_ABI)

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Fee tiers
FEE_TIERS = [100, 500, 3000, 10000]

def get_pool_address(token_a, token_b, fee):
    try:
        pool_address = factory_contract.functions.getPool(token_a, token_b, fee).call()
        return pool_address if pool_address != '0x0000000000000000000000000000000000000000' else None
    except ContractLogicError:
        return None

def get_token_symbol(token_address):
    # This is a placeholder function. In a real-world scenario, you would
    # query the token contract or use a token database to get the actual symbol.
    token_symbols = {
        '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2': 'WETH',
        '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48': 'USDC',
        '0x6B175474E89094C44Da98b954EedeAC495271d0F': 'DAI',
        # Add more token addresses and their symbols here
    }
    return token_symbols.get(token_address, token_address[:6])  # Return first 6 chars of address if symbol not found

def get_slot0_data(pool_address):
    pool_contract = w3.eth.contract(address=pool_address, abi=POOL_ABI)
    return pool_contract.functions.slot0().call()

def sqrt_price_x96_to_price(sqrt_price_x96, token0_decimals, token1_decimals):
    price = (sqrt_price_x96 ** 2) / (2 ** 192)
    decimal_adjustment = 10 ** (token1_decimals - token0_decimals)
    return price * decimal_adjustment

def get_quote(token_in, token_out, fee, amount_in):
    try:
        quote = quoter_contract.functions.quoteExactInputSingle(
            token_in,
            token_out,
            fee,
            amount_in,
            0  # sqrtPriceLimitX96 (0 for no price limit)
        ).call()
        return quote
    except ContractLogicError:
        return None

def fetch_and_store_pools(token_pairs, amount_in=1000000):  # Default 1 USDC (assuming 6 decimals)
    for token_a, token_b in token_pairs:
        token_a_symbol = get_token_symbol(token_a)
        token_b_symbol = get_token_symbol(token_b)
        pool_name = f"{token_a_symbol}/{token_b_symbol}"
        pair_key = f"Uniswap V3:{pool_name}"
        
        pool_exists = False
        for fee in FEE_TIERS:
            pool_address = get_pool_address(token_a, token_b, fee)
            if pool_address:
                fee_key = f"{pair_key}:Fee tier {fee}"
                redis_client.set(fee_key, pool_address)
                
                # Fetch slot0 data
                slot0_data = get_slot0_data(pool_address)
                
                # Convert sqrtPriceX96 to price
                token0_decimals = 18  # Example: WETH has 18 decimals
                token1_decimals = 6   # Example: USDC has 6 decimals
                price = sqrt_price_x96_to_price(slot0_data[0], token0_decimals, token1_decimals)
                
                # Store slot0 data in Redis
                slot0_key = f"{fee_key}:slot0"
                slot0_data_dict = {
                    "sqrtPriceX96": str(slot0_data[0]),
                    "tick": str(slot0_data[1]),
                    "observationIndex": str(slot0_data[2]),
                    "observationCardinality": str(slot0_data[3]),
                    "observationCardinalityNext": str(slot0_data[4]),
                    "feeProtocol": str(slot0_data[5]),
                    "unlocked": str(slot0_data[6]),
                    "price": str(price)
                }
                redis_client.hset(slot0_key, mapping=slot0_data_dict)
                
                # Fetch and store quote
                quote_a_to_b = get_quote(token_a, token_b, fee, amount_in)
                quote_b_to_a = get_quote(token_b, token_a, fee, amount_in)
                
                quote_key = f"{fee_key}:quote"
                quote_data = {
                    f"{token_a_symbol}_to_{token_b_symbol}": str(quote_a_to_b) if quote_a_to_b else "N/A",
                    f"{token_b_symbol}_to_{token_a_symbol}": str(quote_b_to_a) if quote_b_to_a else "N/A",
                    "amount_in": str(amount_in)
                }
                redis_client.hset(quote_key, mapping=quote_data)
                
                pool_exists = True

        # If any pool was found for this pair, add it to the main Uniswap V3 list
        if pool_exists:
            redis_client.sadd("Uniswap V3", pool_name)

def main():
    # Example token pairs (replace with your actual token addresses)
    token_pairs = [
        ('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'),  # WETH/USDC
        ('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', '0x6B175474E89094C44Da98b954EedeAC495271d0F'),  # WETH/DAI
        # Add more token pairs here
    ]

    fetch_and_store_pools(token_pairs)

if __name__ == "__main__":
    main()