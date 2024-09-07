import redis
import json
from collections import defaultdict
import logging
from web3 import Web3

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Connect to Ethereum node (replace with your own node URL)
w3 = Web3(Web3.HTTPProvider('http://localhost:8545'))

# ABIs for Uniswap V2 and V3 pools
UNISWAP_V2_ABI = json.loads('[{"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"stateMutability":"view","type":"function"}]')
UNISWAP_V3_ABI = json.loads('[{"inputs":[{"internalType":"int24","name":"tickLower","type":"int24"},{"internalType":"int24","name":"tickUpper","type":"int24"}],"name":"snapshotCumulativesInside","outputs":[{"internalType":"int56","name":"tickCumulativeInside","type":"int56"},{"internalType":"uint160","name":"secondsPerLiquidityInsideX128","type":"uint160"},{"internalType":"uint32","name":"secondsInside","type":"uint32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"slot0","outputs":[{"internalType":"uint160","name":"sqrtPriceX96","type":"uint160"},{"internalType":"int24","name":"tick","type":"int24"},{"internalType":"uint16","name":"observationIndex","type":"uint16"},{"internalType":"uint16","name":"observationCardinality","type":"uint16"},{"internalType":"uint16","name":"observationCardinalityNext","type":"uint16"},{"internalType":"uint8","name":"feeProtocol","type":"uint8"},{"internalType":"bool","name":"unlocked","type":"bool"}],"stateMutability":"view","type":"function"}]')

# Quoter contract for Uniswap V3
QUOTER_CONTRACT_ADDRESS = '0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6'
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

# Initialize the Quoter contract
quoter_contract = w3.eth.contract(address=w3.to_checksum_address(QUOTER_CONTRACT_ADDRESS), abi=QUOTER_ABI)

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
        self.contract = w3.eth.contract(address=Web3.to_checksum_address(address), abi=UNISWAP_V3_ABI if is_v3 else UNISWAP_V2_ABI)

    def get_price(self, token_in, token_out, amount_in):
        try:
            if self.is_v3:
                return self._get_v3_price(token_in, token_out, amount_in)
            else:
                return self._get_v2_price(token_in, token_out, amount_in)
        except Exception as e:
            logging.error(f"Error fetching price for pool {self.address}: {str(e)}")
            return None

    def _get_v2_price(self, token_in, token_out, amount_in):
        reserves = self.contract.functions.getReserves().call()
        reserve_in = reserves[0] if token_in.address < token_out.address else reserves[1]
        reserve_out = reserves[1] if token_in.address < token_out.address else reserves[0]
        amount_out = (amount_in * reserve_out) / (reserve_in + amount_in)
        logging.info(f"V2 Price from {token_in.symbol} to {token_out.symbol}: {amount_out:.10f}")
        return amount_out

    def _get_v3_price(self, token_in, token_out, amount_in):
        try:
            amount_out = quoter_contract.functions.quoteExactInputSingle(
                token_in.address,
                token_out.address,
                self.fee,
                amount_in,
                0  # sqrtPriceLimitX96, set to 0 to not limit the price
            ).call()
            logging.info(f"V3 Price from {token_in.symbol} to {token_out.symbol}: {amount_out:.10f}")
            return amount_out
        except Exception as e:
            logging.error(f"Error fetching V3 quote: {e}")
            return None

    def swap(self, amount_in, token_in, token_out):
        price = self.get_price(token_in, token_out, amount_in)
        if price is None:
            return 0
        amount_out = price * (1 - self.fee / 1000000)  # Apply fee
        logging.info(f"Swapping {amount_in:.2f} {token_in.symbol} to {amount_out:.2f} {token_out.symbol} with fee {self.fee / 10000:.2f}%")
        return amount_out

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

def simulate_arbitrage(path, initial_amount):
    amount = initial_amount
    logging.info(f"Starting with ${amount:.2f}")

    for i, (pool, token_in, token_out) in enumerate(path, 1):
        amount = pool.swap(amount, token_in, token_out)
        if amount == 0:
            logging.error(f"Failed to perform swap at step {i}")
            return 0
        logging.info(f"Step {i}: {token_in.symbol} -> {token_out.symbol}: ${amount:.2f}")

    profit = amount - initial_amount
    profit_percentage = (profit / initial_amount) * 100
    logging.info(f"Final amount: ${amount:.2f}")
    logging.info(f"Profit: ${profit:.2f} ({profit_percentage:.2f}%)")

    return amount

def main():
    graph = load_specific_configurations_from_redis()
    
    # USDC address
    start_token_address = '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'
    
    paths = generate_arbitrage_paths(graph, start_token_address)
    
    logging.info(f"Generated {len(paths)} potential arbitrage paths")
    logging.info("All potential arbitrage paths:")
    for i, path in enumerate(paths, 1):
        logging.info(f"\nArbitrage Path {i}:")
        logging.info(format_path(path))
        logging.info("Simulating $1000 through the path:")
        final_amount = simulate_arbitrage(path, 1000)
        logging.info("-" * 50)  # Add a separator between paths

if __name__ == "__main__":
    main()
