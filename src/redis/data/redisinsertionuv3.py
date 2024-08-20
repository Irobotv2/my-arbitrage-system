import redis
from web3 import Web3
from web3.exceptions import ContractLogicError
import json
import math
import time
import logging

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

# Add ERC20 ABI for decimals function
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
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

def get_token_decimals(token_address):
    token_contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
    return token_contract.functions.decimals().call()

def get_slot0_data(pool_address):
    pool_contract = w3.eth.contract(address=pool_address, abi=POOL_ABI)
    return pool_contract.functions.slot0().call()

def sqrt_price_x96_to_price(sqrt_price_x96, token0_decimals, token1_decimals):
    price = (sqrt_price_x96 ** 2) / (2 ** 192)
    decimal_adjustment = 10 ** (token1_decimals - token0_decimals)
    return (1 / price) / decimal_adjustment

def get_quote(token_in, token_out, fee, amount_in):
    token_in_decimals = get_token_decimals(token_in)
    token_out_decimals = get_token_decimals(token_out)
    
    # Always quote for 1 unit of token_in
    adjusted_amount_in = 10 ** token_in_decimals
    
    try:
        quote = quoter_contract.functions.quoteExactInputSingle(
            token_in,
            token_out,
            fee,
            adjusted_amount_in,
            0  # sqrtPriceLimitX96 (0 for no price limit)
        ).call()
        
        # Adjust the quote based on the decimals of token_out
        adjusted_quote = quote / (10 ** token_out_decimals)
        
        logging.info(f"Quote details: 1 {get_token_symbol(token_in)} = {adjusted_quote} {get_token_symbol(token_out)}")
        
        return adjusted_quote
    except Exception as e:
        logging.error(f"Error in get_quote: {str(e)}")
        return None
   
def fetch_and_store_pools(token_pairs):
    for token_a, token_b in token_pairs:
        token_a_symbol = get_token_symbol(token_a)
        token_b_symbol = get_token_symbol(token_b)
        token_a_decimals = get_token_decimals(token_a)
        token_b_decimals = get_token_decimals(token_b)
        pool_name = f"{token_a_symbol}/{token_b_symbol}"
        logging.info(f"Processing pool: {pool_name}")
        logging.info(f"Token A: {token_a_symbol}, Address: {token_a}, Decimals: {token_a_decimals}")
        logging.info(f"Token B: {token_b_symbol}, Address: {token_b}, Decimals: {token_b_decimals}")
        
        for fee in FEE_TIERS:
            try:
                pool_address = get_pool_address(token_a, token_b, fee)
                if pool_address:
                    pool_key = f"Uniswap V3:{pool_name}:{fee}"
                    logging.info(f"Found pool address for {pool_key}: {pool_address}")
                    
                    try:
                        slot0_data = get_slot0_data(pool_address)
                        logging.info(f"Fetched slot0 data for {pool_key}: {slot0_data}")
                    except Exception as e:
                        logging.error(f"Error fetching slot0 data for {pool_key}: {str(e)}")
                        continue
                    
                    try:
                        price = sqrt_price_x96_to_price(slot0_data[0], token_a_decimals, token_b_decimals)
                        logging.info(f"Calculated price for {pool_key}: {price}")
                    except Exception as e:
                        logging.error(f"Error calculating price for {pool_key}: {str(e)}")
                        continue
                    
                    try:
                        quote_a_to_b = get_quote(token_a, token_b, fee, 10**token_a_decimals)
                        logging.info(f"Quote {token_a_symbol} to {token_b_symbol} for {pool_key}: {quote_a_to_b}")
                    except Exception as e:
                        logging.error(f"Error getting quote {token_a_symbol} to {token_b_symbol} for {pool_key}: {str(e)}")
                        quote_a_to_b = None
                    
                    try:
                        quote_b_to_a = get_quote(token_b, token_a, fee, 10**token_b_decimals)
                        logging.info(f"Quote {token_b_symbol} to {token_a_symbol} for {pool_key}: {quote_b_to_a}")
                    except Exception as e:
                        logging.error(f"Error getting quote {token_b_symbol} to {token_a_symbol} for {pool_key}: {str(e)}")
                        quote_b_to_a = None
                    
                    pool_data = {
                        "pool_address": pool_address,
                        "sqrtPriceX96": str(slot0_data[0]),
                        "tick": str(slot0_data[1]),
                        "observationIndex": str(slot0_data[2]),
                        "observationCardinality": str(slot0_data[3]),
                        "observationCardinalityNext": str(slot0_data[4]),
                        "feeProtocol": str(slot0_data[5]),
                        "unlocked": str(slot0_data[6]),
                        "price": str(price),
                        f"{token_a_symbol}_to_{token_b_symbol}": str(quote_a_to_b) if quote_a_to_b is not None else "N/A",
                        f"{token_b_symbol}_to_{token_a_symbol}": str(quote_b_to_a) if quote_b_to_a is not None else "N/A",
                        "token_a_decimals": str(token_a_decimals),
                        "token_b_decimals": str(token_b_decimals),
                        "last_updated": str(int(time.time()))
                    }
                    
                    try:
                        redis_client.hset(pool_key, mapping=pool_data)
                        redis_client.expire(pool_key, 300)
                        redis_client.sadd("Uniswap V3", pool_name)
                        logging.info(f"Successfully stored data for pool: {pool_key}")
                    except Exception as e:
                        logging.error(f"Error storing data in Redis for {pool_key}: {str(e)}")
                else:
                    logging.info(f"No pool found for {pool_name} with fee {fee}")
            except Exception as e:
                logging.error(f"Unexpected error processing pool {pool_name} with fee {fee}: {str(e)}")


def test_price_calculation(token_pairs):
    for token_a, token_b in token_pairs:
        token_a_symbol = get_token_symbol(token_a)
        token_b_symbol = get_token_symbol(token_b)
        pool_name = f"{token_a_symbol}/{token_b_symbol}"
        
        for fee in FEE_TIERS:
            pool_key = f"Uniswap V3:{pool_name}:{fee}"
            pool_data = redis_client.hgetall(pool_key)
            
            if pool_data:
                pool_data = {k.decode('utf-8'): v.decode('utf-8') for k, v in pool_data.items()}
                
                calculated_price = float(pool_data['price'])
                quote_a_to_b = float(pool_data[f"{token_a_symbol}_to_{token_b_symbol}"]) if pool_data[f"{token_a_symbol}_to_{token_b_symbol}"] != "N/A" else None
                quote_b_to_a = float(pool_data[f"{token_b_symbol}_to_{token_a_symbol}"]) if pool_data[f"{token_b_symbol}_to_{token_a_symbol}"] != "N/A" else None
                
                logging.info(f"Pool: {pool_key}")
                logging.info(f"Calculated price from sqrtPrice (1 {token_a_symbol} = {calculated_price} {token_b_symbol})")
                logging.info(f"Quote: 1 {token_a_symbol} = {quote_a_to_b} {token_b_symbol}")
                logging.info(f"Quote: 1 {token_b_symbol} = {quote_b_to_a} {token_a_symbol}")
                
                if quote_a_to_b and quote_b_to_a:
                    # Calculate price difference for both directions
                    price_diff_a_to_b = abs(calculated_price - quote_a_to_b) / quote_a_to_b
                    price_diff_b_to_a = abs(1/calculated_price - quote_b_to_a) / quote_b_to_a
                    
                    logging.info(f"Price difference ({token_a_symbol} to {token_b_symbol}): {price_diff_a_to_b:.2%}")
                    logging.info(f"Price difference ({token_b_symbol} to {token_a_symbol}): {price_diff_b_to_a:.2%}")
                    
                    if price_diff_a_to_b > 0.01 or price_diff_b_to_a > 0.01:  # More than 1% difference
                        logging.warning(f"Large price discrepancy detected in {pool_key}")
                    else:
                        logging.info(f"Prices match within 1% tolerance for {pool_key}")
                    
                    # Calculate and log liquidity metrics
                    liquidity = int(pool_data.get('liquidity', 0))
                    logging.info(f"Pool liquidity: {liquidity}")
                    
                    # You might want to add more metrics here, such as:
                    # - Time since last trade
                    # - 24h volume
                    # - Price range of concentrated liquidity
                    
                    # Example of additional check for low liquidity pools
                    if liquidity < 1000000:  # This is an arbitrary threshold, adjust as needed
                        logging.warning(f"Low liquidity detected in {pool_key}")
                else:
                    logging.warning(f"Unable to test price calculation for {pool_key} due to missing quote data")
def main():
    logging.basicConfig(level=logging.INFO)
    
    token_pairs = [
        ('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'),  # WETH/USDC
        ('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', '0x6B175474E89094C44Da98b954EedeAC495271d0F'),  # WETH/DAI
    ]

    logging.info("Starting Uniswap V3 data collection")
    fetch_and_store_pools(token_pairs)
    logging.info("Finished Uniswap V3 data collection")
    
    logging.info("Starting price calculation test")
    test_price_calculation(token_pairs)
    logging.info("Finished price calculation test")

if __name__ == "__main__":
    main()