import redis
import json
import logging
import time
from collections import defaultdict
from web3 import Web3

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

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

# Initialize Uniswap V3 Quoter contract
quoter_contract = w3.eth.contract(address=w3.to_checksum_address(QUOTER_CONTRACT_ADDRESS), abi=QUOTER_ABI)

# Full Uniswap V2 Pair ABI
UNISWAP_V2_PAIR_ABI = json.loads('''
[
    {
        "constant": true,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"internalType": "uint112", "name": "_reserve0", "type": "uint112"},
            {"internalType": "uint112", "name": "_reserve1", "type": "uint112"},
            {"internalType": "uint32", "name": "_blockTimestampLast", "type": "uint32"}
        ],
        "payable": false,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": true,
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "payable": false,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": true,
        "inputs": [],
        "name": "token1",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "payable": false,
        "stateMutability": "view",
        "type": "function"
    }
]
''')

# Define token decimals
TOKEN_DECIMALS = {
    '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48': 6,  # USDC
    '0x6b175474e89094c44da98b954eedeac495271d0f': 18, # DAI
    '0xc02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2': 18, # WETH
    '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599': 8,  # WBTC
    # Add more tokens and their decimals as needed
}

def get_token_decimals(token_address):
    return TOKEN_DECIMALS.get(token_address.lower(), 18)  # Default to 18 if not found

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

def load_configurations_from_redis():
    logging.info("Loading configurations from Redis...")
    graph = PoolGraph()
    
    # List all the configuration keys in Redis to be loaded
    configuration_keys = ['USDC_WETH_config', 'WETH_DAI_config', 'DAI_WBTC_config']

    for config_key in configuration_keys:
        config_json = redis_client.get(config_key)
        if config_json:
            config = json.loads(config_json)
            token0 = Token(config['token0']['address'], config['token0']['symbol'])
            token1 = Token(config['token1']['address'], config['token1']['symbol'])
            graph.add_token(token0)
            graph.add_token(token1)

            # Add Uniswap V2 pool
            if config.get('v2_pool'):
                pool = Pool(config['v2_pool'], token0, token1, 3000, False)
                graph.add_pool(pool)

            # Add Uniswap V3 pools
            for fee_tier, v3_pool_info in config.get('v3_pools', {}).items():
                pool = Pool(v3_pool_info['address'], token0, token1, int(float(fee_tier[:-1]) * 10000), True)
                graph.add_pool(pool)

    logging.info(f"Loaded {len(graph.tokens)} tokens and {len(graph.pools)} pools from configurations")
    return graph

def generate_arbitrage_paths(graph):
    paths = []

    for start_token_address in graph.tokens.keys():
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

    logging.info(f"Generated {len(paths)} potential arbitrage paths")
    return paths

def format_path(path):
    result = ["Path:"]
    for i, (pool, token_in, token_out) in enumerate(path, 1):
        pool_type = "V2" if not pool.is_v3 else f"V3/{pool.fee/10000:.2f}%"
        result.append(f"{i}: {token_in.symbol} -> {token_out.symbol} ({pool_type})")
    return "\n".join(result)

def calculate_execution_price(amount_in, token_in, token_out, pair_contract):
    token0_address = pair_contract.functions.token0().call()
    token1_address = pair_contract.functions.token1().call()

    reserve0, reserve1 = get_reserves(pair_contract, token0_address, token1_address)
    if reserve0 is None or reserve1 is None:
        logging.error("Reserves not fetched correctly. Aborting execution price calculation.")
        return None

    decimals_in = get_token_decimals(token_in)
    decimals_out = get_token_decimals(token_out)
    amount_in_human = amount_in / (10 ** decimals_in)

    if token_in == token0_address:
        amount_out = (amount_in_human * reserve1) / (reserve0 + amount_in_human)
    else:
        amount_out = (amount_in_human * reserve0) / (reserve1 + amount_in_human)

    amount_out = amount_out * (10 ** decimals_out)
    
    logging.info(f"Execution Price: {amount_in_human} {token_in} -> {amount_out} {token_out}")
    return amount_out

def get_reserves(pair_contract, token0_address, token1_address):
    try:
        reserves = pair_contract.functions.getReserves().call()
        decimals0 = get_token_decimals(token0_address)
        decimals1 = get_token_decimals(token1_address)
        reserve0 = reserves[0] / (10 ** decimals0)
        reserve1 = reserves[1] / (10 ** decimals1)
        return reserve0, reserve1
    except Exception as e:
        logging.error(f"Error fetching reserves: {e}")
        return None, None

def get_quote(token_in, token_out, amount_in, fee_tier):
    try:
        amount_out = quoter_contract.functions.quoteExactInputSingle(
            token_in,
            token_out,
            fee_tier,
            int(amount_in),  
            0  
        ).call()

        return amount_out

    except Exception as e:
        logging.error(f"Error fetching quote for {token_in} -> {token_out} with amount {amount_in}: {e}")
        return None

def log_arbitrage_opportunity(path, input_amount, output_amount):
    with open("arbitrage_opportunities.log", "a") as log_file:
        log_file.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_file.write(format_path(path) + "\n")
        log_file.write(f"Input Amount: {input_amount:.6f} {path[0][1].symbol}\n")
        log_file.write(f"Output Amount: {output_amount:.6f} {path[0][1].symbol}\n")
        log_file.write(f"Profit: {output_amount - input_amount:.6f} {path[0][1].symbol}\n")
        log_file.write(f"Profit %: {((output_amount - input_amount) / input_amount) * 100:.2f}%\n")
        log_file.write("-" * 50 + "\n")

def simulate_arbitrage_for_path(path):
    starting_token = path[0][1]
    decimals_starting_token = get_token_decimals(starting_token.address)
    starting_amount = 1000  

    starting_amount_in = starting_amount * (10 ** decimals_starting_token)

    logging.info(format_path(path))

    pool1, token_in, token_out = path[0]
    if not pool1.is_v3:
        pair_contract = w3.eth.contract(address=pool1.address, abi=UNISWAP_V2_PAIR_ABI)
        amount_out = calculate_execution_price(starting_amount_in, token_in.address, token_out.address, pair_contract)
    else:
        amount_out = get_quote(token_in.address, token_out.address, starting_amount_in, pool1.fee)

    if amount_out is None:
        logging.error("Failed to get amount out for first swap. Aborting path simulation.")
        return

    logging.info(f"Initial token amount: {starting_amount} {starting_token.symbol}")
    logging.info(f"1: Input {starting_amount} {starting_token.symbol} -> Output {amount_out / (10 ** get_token_decimals(token_out.address)):.6f} {token_out.symbol} ({pool1.fee/10000:.2f}% fee)")

    pool2, token_in, token_out = path[1]
    if pool2.is_v3:
        final_amount = get_quote(token_in.address, token_out.address, amount_out, pool2.fee)
    else:
        pair_contract = w3.eth.contract(address=pool2.address, abi=UNISWAP_V2_PAIR_ABI)
        final_amount = calculate_execution_price(amount_out, token_in.address, token_out.address, pair_contract)

    if final_amount is None:
        logging.error("Failed to get final amount for second swap. Aborting path simulation.")
        return

    final_amount_hr = final_amount / (10 ** decimals_starting_token)
    logging.info(f"2: Input {amount_out / (10 ** get_token_decimals(token_in.address)):.6f} {token_in.symbol} -> Output {final_amount_hr:.6f} {starting_token.symbol} ({pool2.fee/10000:.2f}% fee)")

    profit = final_amount_hr - starting_amount
    profit_percentage = (profit / starting_amount) * 100 if starting_amount != 0 else 0
    logging.info(f"Final Token Amount: {final_amount_hr:.6f} {starting_token.symbol}")
    logging.info(f"Profit: {profit:.6f} {starting_token.symbol}")
    logging.info(f"Profit %: {profit_percentage:.2f}%")
    logging.info("-" * 50)

    if profit > 0:
        log_arbitrage_opportunity(path, starting_amount, final_amount_hr)

def main():
    graph = load_configurations_from_redis()
    paths = generate_arbitrage_paths(graph)
    
    logging.info(f"Generated {len(paths)} potential arbitrage paths")
    
    try:
        while True:
            for i, path in enumerate(paths, 1):
                simulate_arbitrage_for_path(path)
            
            time.sleep(60)  # Wait for 60 seconds before the next round
    except KeyboardInterrupt:
        logging.info("Script stopped by user.")

if __name__ == "__main__":
    main()
