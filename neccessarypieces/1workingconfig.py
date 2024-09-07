import redis
import json
import logging
from collections import defaultdict
from web3 import Web3

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define constants for the Ethereum node
INFURA_URL = 'http://localhost:8545'  # Replace with your Ethereum node URL
QUOTER_CONTRACT_ADDRESS = '0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6'  # Uniswap V3 Quoter contract address on Ethereum mainnet

# Uniswap V3 Quoter ABI
QUOTER_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenIn", "type": "address"},
            {"internalType": "address", "name": "tokenOut", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"},
        ],
        "name": "quoteExactInputSingle",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Connect to the Ethereum node
w3 = Web3(Web3.HTTPProvider(INFURA_URL))

# Convert addresses to checksum format
USDC_ADDRESS = w3.to_checksum_address('0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48')
WETH_ADDRESS = w3.to_checksum_address('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2')

# Initialize the Uniswap V3 Quoter contract
quoter_contract = w3.eth.contract(address=w3.to_checksum_address(QUOTER_CONTRACT_ADDRESS), abi=QUOTER_ABI)

# Uniswap V2 Pair ABI
UNISWAP_V2_PAIR_ABI = json.loads('[{"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"stateMutability":"view","type":"function"}]')

class Token:
    def __init__(self, address, symbol):
        self.address = address
        self.symbol = symbol

class Pool:
    def __init__(self, address, token0, token1, fee, is_v3):
        self.address = address
        self.token0 = token0
        self.token1 = token1
        self.fee = fee
        self.is_v3 = is_v3

class PoolGraph:
    def __init__(self):
        self.tokens = {}  # address -> Token
        self.pools = []   # List of all pools
        self.edges = defaultdict(lambda: defaultdict(list))  # token_address -> token_address -> [Pool]

    def add_token(self, token):
        if token.address not in self.tokens:
            self.tokens[token.address] = token

    def add_pool(self, pool):
        self.pools.append(pool)
        self.edges[pool.token0.address][pool.token1.address].append(pool)
        self.edges[pool.token1.address][pool.token0.address].append(pool)

def load_specific_configurations_from_redis():
    logging.info("Loading specific configurations from Redis...")
    graph = PoolGraph()
    specific_configs = ['USDC_WETH_config', 'WETH_DAI_config', 'DAI_WBTC_config']
    
    for config_key in specific_configs:
        config_json = redis_client.get(config_key)
        if config_json:
            config = json.loads(config_json)
            token0 = Token(config['token0']['address'], config['token0']['symbol'])
            token1 = Token(config['token1']['address'], config['token1']['symbol'])
            graph.add_token(token0)
            graph.add_token(token1)

            if config.get('v2_pool'):
                pool = Pool(config['v2_pool'], token0, token1, 3000, False)
                graph.add_pool(pool)

            for fee_tier, v3_pool_info in config.get('v3_pools', {}).items():
                pool = Pool(v3_pool_info['address'], token0, token1, int(float(fee_tier[:-1]) * 10000), True)
                graph.add_pool(pool)

    logging.info(f"Loaded {len(graph.tokens)} tokens and {len(graph.pools)} pools")
    return graph

def generate_arbitrage_paths(graph, start_token_address):
    paths = []
    start_token = graph.tokens[start_token_address]

    for first_pool in graph.edges[start_token_address].values():
        for pool1 in first_pool:
            other_token = pool1.token1 if pool1.token0.address == start_token_address else pool1.token0
            for second_pool in graph.edges[other_token.address][start_token_address]:
                if pool1 != second_pool:
                    path = [
                        (pool1, start_token, other_token),
                        (second_pool, other_token, start_token)
                    ]
                    paths.append(path)

    return paths

def format_path(path):
    result = ["Path:"]
    for i, (pool, token_in, token_out) in enumerate(path, 1):
        pool_type = "V2" if not pool.is_v3 else f"V3/{pool.fee/10000:.2f}%"
        result.append(f"{i}: {token_in.symbol} -> {token_out.symbol} ({pool_type})")

    result.append("\n0x addresses of pools:")
    for i, (pool, token_in, token_out) in enumerate(path, 1):
        result.append(f"{i}:")
        result.append(f"a input token id: {token_in.address}")
        result.append(f"b output token id: {token_out.address}")
        result.append(f"pool: {pool.address}")

    return "\n".join(result)

def get_reserves(pair_contract):
    reserves = pair_contract.functions.getReserves().call()
    reserve_usdc = reserves[0] / (10 ** 6)  # Convert to human-readable format
    reserve_weth = reserves[1] / (10 ** 18)  # Convert to human-readable format
    logging.info(f"Reserves - USDC: {reserve_usdc}, WETH: {reserve_weth}")
    return reserve_usdc, reserve_weth

def calculate_execution_price(amount_in, token_in, token_out, pair_contract):
    reserve_usdc, reserve_weth = get_reserves(pair_contract)
    if token_in == USDC_ADDRESS:
        amount_in = amount_in / (10 ** 6)  # Convert USDC to human-readable
    elif token_in == WETH_ADDRESS:
        amount_in = amount_in / (10 ** 18)  # Convert WETH to human-readable
    else:
        raise ValueError("Invalid token addresses")

    if token_in == USDC_ADDRESS and token_out == WETH_ADDRESS:
        amount_out = (amount_in * reserve_weth) / (reserve_usdc + amount_in)
    elif token_in == WETH_ADDRESS and token_out == USDC_ADDRESS:
        amount_out = (amount_in * reserve_usdc) / (reserve_weth + amount_in)
    else:
        raise ValueError("Invalid token addresses")

    if token_out == USDC_ADDRESS:
        amount_out = amount_out * (10 ** 6)  # Convert back to smallest unit
    elif token_out == WETH_ADDRESS:
        amount_out = amount_out * (10 ** 18)  # Convert back to smallest unit

    logging.info(f"Execution Price: {amount_in} {token_in} -> {amount_out} {token_out}")
    return amount_out

def get_quote(token_in, token_out, amount_in, fee_tier):
    try:
        amount_out = quoter_contract.functions.quoteExactInputSingle(
            token_in,
            token_out,
            fee_tier,
            int(amount_in),  # Input amount
            0  # sqrtPriceLimitX96, set to 0 to not limit the price
        ).call()

        logging.info(f"Quote: {amount_in / (10 ** 18)} {token_in} -> {amount_out / (10 ** 6):.6f} {token_out}")
        return amount_out

    except Exception as e:
        logging.error(f"Error fetching quote: {e}")
        return None

def simulate_arbitrage_for_path(path):
    # Determine the starting token dynamically
    starting_token = path[0][1]
    starting_amount = 1000  # Starting amount (in human-readable format)

    if starting_token.address == USDC_ADDRESS:
        starting_amount_in = starting_amount * (10 ** 6)  # Convert USDC to smallest unit
    elif starting_token.address == WETH_ADDRESS:
        starting_amount_in = starting_amount * (10 ** 18)  # Convert WETH to smallest unit
    else:
        # Handle other token decimals if needed
        starting_amount_in = starting_amount * (10 ** 18)  # Example, adjust based on token decimals

    logging.info(f"Starting amount: {starting_amount} {starting_token.symbol}")

    # Process first swap
    pool1, token_in, token_out = path[0]
    if not pool1.is_v3:
        pair_contract = w3.eth.contract(address=pool1.address, abi=UNISWAP_V2_PAIR_ABI)
        amount_out = calculate_execution_price(starting_amount_in, token_in.address, token_out.address, pair_contract)
    else:
        amount_out = get_quote(token_in.address, token_out.address, starting_amount_in, pool1.fee)

    # Process second swap
    pool2, token_in, token_out = path[1]
    if pool2.is_v3:
        final_amount = get_quote(token_in.address, token_out.address, amount_out, pool2.fee)
    else:
        pair_contract = w3.eth.contract(address=pool2.address, abi=UNISWAP_V2_PAIR_ABI)
        final_amount = calculate_execution_price(amount_out, token_in.address, token_out.address, pair_contract)

    # Convert the final amount back to human-readable format
    if starting_token.address == USDC_ADDRESS:
        final_amount_hr = final_amount / (10 ** 6)
    elif starting_token.address == WETH_ADDRESS:
        final_amount_hr = final_amount / (10 ** 18)
    else:
        # Handle other token decimals if needed
        final_amount_hr = final_amount / (10 ** 18)  # Example, adjust based on token decimals

    # Log the final results
    logging.info(f"Ending amount: {final_amount_hr:.6f} {starting_token.symbol}")
    profit = final_amount_hr - starting_amount
    logging.info(f"Arbitrage Profit: {profit:.6f} {starting_token.symbol}")

def main():
    graph = load_specific_configurations_from_redis()
    start_token_address = USDC_ADDRESS  # This can be adjusted to other starting tokens if needed
    paths = generate_arbitrage_paths(graph, start_token_address)
    
    logging.info(f"Generated {len(paths)} potential arbitrage paths")
    for i, path in enumerate(paths, 1):
        logging.info(f"\nSimulating Arbitrage Path {i}:")
        logging.info(format_path(path))
        simulate_arbitrage_for_path(path)
        logging.info("-" * 50)

if __name__ == "__main__":
    main()
