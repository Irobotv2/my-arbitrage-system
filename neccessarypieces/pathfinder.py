import redis
import json
from collections import defaultdict
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

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
        logging.info("-" * 50)  # Add a separator between paths

if __name__ == "__main__":
    main()