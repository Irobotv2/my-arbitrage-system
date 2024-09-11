import redis
import json
import logging
from collections import defaultdict

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
main_logger = logging.getLogger('main')
data_detection_logger = logging.getLogger('data_detection')
liquidity_vault_logger = logging.getLogger('liquidity_vault')
execution_logger = logging.getLogger('execution')

# File handlers for specific logs
data_detection_file = logging.FileHandler('data_detection.log')
liquidity_vault_file = logging.FileHandler('liquidity_vault.log')
execution_file = logging.FileHandler('execution.log')

data_detection_logger.addHandler(data_detection_file)
liquidity_vault_logger.addHandler(liquidity_vault_file)
execution_logger.addHandler(execution_file)

# Assuming these classes are defined as in your original script
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
        self.tokens = {}
        self.pools = []
        self.edges = defaultdict(lambda: defaultdict(list))

    def add_token(self, token):
        if token.address not in self.tokens:
            self.tokens[token.address] = token

    def add_pool(self, pool):
        self.pools.append(pool)
        self.edges[pool.token0.address][pool.token1.address].append(pool)
        self.edges[pool.token1.address][pool.token0.address].append(pool)

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

def load_configurations_from_redis():
    data_detection_logger.info("Loading configurations from Redis...")
    graph = PoolGraph()
    
    # Dynamically fetch all keys from Redis
    configuration_keys = [key.decode('utf-8') for key in redis_client.keys('*_config')]

    for config_key in configuration_keys:
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

    data_detection_logger.info(f"Loaded {len(graph.tokens)} tokens and {len(graph.pools)} pools from configurations")
    return graph

# Function to generate complex arbitrage paths
def generate_unique_complex_arbitrage_paths(graph, max_hops=4, max_paths=1000):
    paths = []
    unique_paths = set()
    for start_token_address in graph.tokens.keys():
        start_token = graph.tokens[start_token_address]
        stack = [(start_token, [], set())]
        
        while stack and len(paths) < max_paths:
            current_token, current_path, visited = stack.pop()
            
            if len(current_path) > 0 and current_token == start_token:
                path_signature = tuple((p.address, t_in.address, t_out.address) for p, t_in, t_out in current_path)
                if path_signature not in unique_paths:
                    paths.append(current_path)
                    unique_paths.add(path_signature)
                continue
            
            if len(current_path) >= max_hops:
                continue
            
            for next_token_address in graph.edges[current_token.address]:
                next_token = graph.tokens[next_token_address]
                if next_token in visited and next_token != start_token:
                    continue
                
                for pool in graph.edges[current_token.address][next_token_address]:
                    new_path = current_path + [(pool, current_token, next_token)]
                    new_visited = visited.union({next_token})
                    stack.append((next_token, new_path, new_visited))
    
    data_detection_logger.info(f"Generated {len(paths)} unique potential complex arbitrage paths")
    return paths

def format_path(path):
    result = ["Path:"]
    for i, (pool, token_in, token_out) in enumerate(path, 1):
        pool_type = "V2" if not pool.is_v3 else f"V3/{pool.fee/10000:.2f}%"
        result.append(f"{i}: {token_in.symbol} -> {token_out.symbol} ({pool_type})")
    return "\n".join(result)

# Test function
def test_complex_path_generation():
    graph = load_configurations_from_redis()
    paths = generate_complex_arbitrage_paths(graph)
    
    print(f"Generated {len(paths)} complex arbitrage paths")
    
    # Print the first 5 paths for inspection
    for i, path in enumerate(paths[:5], 1):
        print(f"\nPath {i}:")
        print(format_path(path))

def test_unique_complex_path_generation():
    graph = load_configurations_from_redis()
    paths = generate_unique_complex_arbitrage_paths(graph)
    
    print(f"Generated {len(paths)} unique complex arbitrage paths")
    
    # Print the first 5 paths for inspection
    for i, path in enumerate(paths[:5], 1):
        print(f"\nPath {i}:")
        print(format_path(path))
    
    # Verify uniqueness
    unique_signatures = set(tuple((p.address, t_in.address, t_out.address) for p, t_in, t_out in path) for path in paths)
    print(f"\nNumber of unique path signatures: {len(unique_signatures)}")
    print(f"All paths are unique: {len(paths) == len(unique_signatures)}")

if __name__ == "__main__":
    test_unique_complex_path_generation()