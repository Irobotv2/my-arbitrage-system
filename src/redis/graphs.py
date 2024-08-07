import redis
from decimal import Decimal
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Graph:
    def __init__(self):
        self.edges = {}

    def add_edge(self, from_token, to_token, pool, is_v3, fee, price):
        if from_token not in self.edges:
            self.edges[from_token] = []
        self.edges[from_token].append((to_token, pool, is_v3, fee, price))

def fetch_pool_data_from_redis():
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        v2_pairs = {}
        v3_pools = {}
        for key in r.scan_iter("uniswap_v2_pairs:*"):
            if r.type(key) == b'hash':
                pair_data = r.hgetall(key)
                v2_pairs[key.decode()] = {k.decode(): v.decode() for k, v in pair_data.items()}
        for key in r.scan_iter("uniswap_v3_pools:*"):
            if r.type(key) == b'hash':
                pool_data = r.hgetall(key)
                v3_pools[key.decode()] = {k.decode(): v.decode() for k, v in pool_data.items()}
        
        logger.info(f"Fetched {len(v2_pairs)} V2 pairs and {len(v3_pools)} V3 pools from Redis")
        return v2_pairs, v3_pools
    except redis.RedisError as e:
        logger.error(f"Error fetching data from Redis: {e}")
        return {}, {}

def process_v2_pair_data(pair_data):
    try:
        token0 = pair_data.get('token0_address')
        token1 = pair_data.get('token1_address')
        reserve0 = Decimal(pair_data.get('reserve0', '0'))
        reserve1 = Decimal(pair_data.get('reserve1', '0'))
        
        if token0 and token1 and reserve0 and reserve1:
            price0 = reserve1 / reserve0
            price1 = reserve0 / reserve1
            return {
                'token0': token0,
                'token1': token1,
                'address': pair_data.get('pool_address', ''),
                'fee': Decimal('0.003'),
                'price0': price0,
                'price1': price1
            }
        else:
            return None
    except Exception as e:
        logger.error(f"Error processing V2 pair data: {e}")
        return None

def process_v3_pool_data(pool_data):
    try:
        token0 = pool_data.get('token0_address')
        token1 = pool_data.get('token1_address')
        sqrtPriceX96 = Decimal(pool_data.get('sqrt_price', '0'))
        fee_tier = pool_data.get('fee_tier', '')
        
        if token0 and token1 and sqrtPriceX96 and fee_tier:
            fee = Decimal(fee_tier) / Decimal('1000000')
            price = (sqrtPriceX96 / Decimal(2**96)) ** 2
            return {
                'token0': token0,
                'token1': token1,
                'address': pool_data.get('pool_address', ''),
                'fee': fee,
                'price0': price,
                'price1': 1/price
            }
        else:
            return None
    except Exception as e:
        logger.error(f"Error processing V3 pool data: {e}")
        return None

def build_graph(v2_pairs, v3_pools):
    graph = Graph()
    v2_complete = 0
    v3_complete = 0
    
    for key, pair_data in v2_pairs.items():
        processed_data = process_v2_pair_data(pair_data)
        if processed_data:
            graph.add_edge(processed_data['token0'], processed_data['token1'], processed_data['address'], False, processed_data['fee'], processed_data['price0'])
            graph.add_edge(processed_data['token1'], processed_data['token0'], processed_data['address'], False, processed_data['fee'], processed_data['price1'])
            v2_complete += 1
        else:
            logger.warning(f"Incomplete data for V2 pair {key}")

    for key, pool_data in v3_pools.items():
        processed_data = process_v3_pool_data(pool_data)
        if processed_data:
            graph.add_edge(processed_data['token0'], processed_data['token1'], processed_data['address'], True, processed_data['fee'], processed_data['price0'])
            graph.add_edge(processed_data['token1'], processed_data['token0'], processed_data['address'], True, processed_data['fee'], processed_data['price1'])
            v3_complete += 1
        else:
            logger.warning(f"Incomplete data for V3 pool {key}")

    logger.info(f"Built graph with {len(graph.edges)} tokens")
    logger.info(f"Complete V2 pairs: {v2_complete}/{len(v2_pairs)}")
    logger.info(f"Complete V3 pools: {v3_complete}/{len(v3_pools)}")
    return graph

def main():
    v2_pairs, v3_pools = fetch_pool_data_from_redis()
    if not v2_pairs and not v3_pools:
        logger.error("No pool data fetched from Redis")
        return

    # Log sample data
    if v2_pairs:
        sample_v2 = next(iter(v2_pairs.items()))
        logger.info(f"Sample V2 pair data: {sample_v2}")
    if v3_pools:
        sample_v3 = next(iter(v3_pools.items()))
        logger.info(f"Sample V3 pool data: {sample_v3}")

    graph = build_graph(v2_pairs, v3_pools)
    
    # Print some information about the graph
    logger.info(f"Number of tokens in the graph: {len(graph.edges)}")
    if graph.edges:
        sample_token = next(iter(graph.edges))
        logger.info(f"Sample edges for token {sample_token}: {graph.edges[sample_token][:5]}")

if __name__ == "__main__":
    main()