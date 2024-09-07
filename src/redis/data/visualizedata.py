import redis
import json
import os
import logging
import matplotlib.pyplot as plt
import networkx as nx
from collections import defaultdict

# Initialize logging
logging.basicConfig(level=logging.INFO)

# Connect to Redis using environment variables
redis_host = os.getenv('REDIS_HOST', 'localhost')
redis_port = os.getenv('REDIS_PORT', 6379)
redis_db = os.getenv('REDIS_DB', 0)
redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_db)

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
        self.edges = defaultdict(list)  # token_address -> [Pool]

    def add_token(self, token):
        if token.address not in self.tokens:
            self.tokens[token.address] = token

    def add_pool(self, pool):
        self.edges[pool.token0.address].append(pool)
        self.edges[pool.token1.address].append(pool)

def load_configurations_from_redis():
    logging.info("Loading configurations from Redis...")
    graph = PoolGraph()
    for key in redis_client.keys('*_config'):
        config = json.loads(redis_client.get(key))
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

    logging.info(f"Loaded {len(graph.tokens)} tokens and {sum(len(pools) for pools in graph.edges.values())//2} pools")
    return graph

def generate_paths(graph, start_token_address, max_hops=3):
    logging.info(f"Generating paths from {start_token_address} with max {max_hops} hops...")
    
    def dfs(current_token, path, visited):
        if len(path) > max_hops:
            yield path
            return

        for pool in graph.edges[current_token.address]:
            next_token = pool.token1 if pool.token0.address == current_token.address else pool.token0
            if next_token.address not in visited:
                new_path = path + [pool]
                if len(new_path) == max_hops and next_token.address == start_token_address:
                    yield new_path
                else:
                    yield from dfs(next_token, new_path, visited | {next_token.address})

    start_token = graph.tokens[start_token_address]
    paths = list(dfs(start_token, [], {start_token_address}))
    
    logging.info(f"Generated {len(paths)} paths")
    return paths

def visualize_pools_and_paths(graph, paths):
    G = nx.Graph()

    # Add all nodes and edges
    for token_address, pools in graph.edges.items():
        token = graph.tokens[token_address]
        G.add_node(token.symbol)
        for pool in pools:
            other_token = pool.token1 if pool.token0.address == token_address else pool.token0
            G.add_edge(token.symbol, other_token.symbol, 
                       color='blue' if pool.is_v3 else 'green', 
                       weight=2)

    # Highlight paths
    path_edges = set()
    for path in paths[:10]:  # Highlight only the first 10 paths
        for i in range(len(path) - 1):
            token1 = path[i].token0.symbol if path[i].token0.address == path[i+1].token0.address or path[i].token0.address == path[i+1].token1.address else path[i].token1.symbol
            token2 = path[i+1].token0.symbol if path[i+1].token0.address != path[i].token0.address and path[i+1].token0.address != path[i].token1.address else path[i+1].token1.symbol
            path_edges.add((token1, token2))

    # Draw the graph
    plt.figure(figsize=(20, 16))
    pos = nx.spring_layout(G, k=0.5, iterations=50)
    
    # Draw all edges
    nx.draw_networkx_edges(G, pos, edge_color=[G[u][v]['color'] for u,v in G.edges()], width=1)
    
    # Draw highlighted path edges
    nx.draw_networkx_edges(G, pos, edgelist=path_edges, edge_color='red', width=2)
    
    # Draw nodes
    nx.draw_networkx_nodes(G, pos, node_color='skyblue', node_size=3000)
    nx.draw_networkx_labels(G, pos, font_size=8, font_weight='bold')

    plt.title("Uniswap Pools and Generated Paths")
    plt.axis('off')
    plt.tight_layout()
    plt.savefig('uniswap_pools_and_paths.png', dpi=300, bbox_inches='tight')
    print("Plot saved as 'uniswap_pools_and_paths.png'")

if __name__ == "__main__":
    graph = load_configurations_from_redis()
    
    if graph.tokens:
        # Generate paths starting from USDC
        start_token_address = '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'  # USDC address
        paths = generate_paths(graph, start_token_address, max_hops=4)
        
        # Visualize pools and paths
        visualize_pools_and_paths(graph, paths)
    else:
        logging.info("No configurations found in Redis.")