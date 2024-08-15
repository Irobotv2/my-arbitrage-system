import asyncio
import redis
import logging
from datetime import datetime
from decimal import Decimal

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Redis configuration
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_DB = 0

# Constants
PRICE_DEVIATION_THRESHOLD = 0.005  # 0.5%

# Initialize Redis client
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

def redis_operation_with_retry(operation, max_retries=3, delay=1):
    for _ in range(max_retries):
        try:
            return operation()
        except redis.RedisError as e:
            logger.warning(f"Redis operation failed: {str(e)}. Retrying...")
            asyncio.sleep(delay)
    logger.error(f"Redis operation failed after {max_retries} retries")
    return None

async def find_similar_pairs():
    v2_pairs = redis_operation_with_retry(lambda: redis_client.keys("uniswap_v2_pair:*"))
    v3_pools = redis_operation_with_retry(lambda: redis_client.keys("uniswap_v3_pool:*"))
    
    similar_pairs = []
    v2_pair_tokens = {}
    
    for pair_key in v2_pairs:
        pair_data = redis_operation_with_retry(lambda: redis_client.hgetall(pair_key))
        if pair_data and 'token0' in pair_data and 'token1' in pair_data:
            token_pair = frozenset([pair_data['token0'], pair_data['token1']])
            v2_pair_tokens[token_pair] = pair_key
    
    for pool_key in v3_pools:
        pool_data = redis_operation_with_retry(lambda: redis_client.hgetall(pool_key))
        if pool_data and 'token0' in pool_data and 'token1' in pool_data:
            token_pair = frozenset([pool_data['token0'], pool_data['token1']])
            if token_pair in v2_pair_tokens:
                similar_pairs.append((v2_pair_tokens[token_pair], pool_key))
    
    logger.info(f"Found {len(similar_pairs)} similar pairs across Uniswap V2 and V3")
    return similar_pairs

def calculate_v2_price(pool_data):
    try:
        reserve0 = Decimal(pool_data['reserve0'])
        reserve1 = Decimal(pool_data['reserve1'])
        if reserve0 == 0:
            return None
        return reserve1 / reserve0
    except (KeyError, ValueError, ZeroDivisionError):
        return None

def calculate_v3_price(pool_data):
    try:
        sqrt_price_x96 = Decimal(pool_data['sqrtPriceX96'])
        price = (sqrt_price_x96 ** 2) / (2 ** 192)
        return price
    except (KeyError, ValueError):
        return None

def get_token_symbol(token_address):
    token_data = redis_operation_with_retry(lambda: redis_client.hgetall(f"token:{token_address}"))
    return token_data.get('symbol', 'Unknown') if token_data else 'Unknown'

async def compare_pair_prices(v2_pair_key, v3_pool_key):
    v2_data = redis_operation_with_retry(lambda: redis_client.hgetall(v2_pair_key))
    v3_data = redis_operation_with_retry(lambda: redis_client.hgetall(v3_pool_key))
    
    if not v2_data or not v3_data:
        return None
    
    v2_price = calculate_v2_price(v2_data)
    v3_price = calculate_v3_price(v3_data)
    
    if v2_price is None or v3_price is None:
        return None
    
    deviation = abs(v2_price - v3_price) / min(v2_price, v3_price)
    token0_symbol = get_token_symbol(v2_data['token0'])
    token1_symbol = get_token_symbol(v2_data['token1'])
    pair_name = f"{token0_symbol}/{token1_symbol}"
    
    return {
        'pair': pair_name,
        'v2_price': v2_price,
        'v3_price': v3_price,
        'deviation': deviation,
        'v2_key': v2_pair_key,
        'v3_key': v3_pool_key
    }

async def main():
    logger.info("Starting Uniswap V2/V3 pair comparison")
    
    similar_pairs = await find_similar_pairs()
    logger.info(f"Found {len(similar_pairs)} similar pairs for comparison")
    
    results = []
    for v2_pair, v3_pool in similar_pairs:
        comparison = await compare_pair_prices(v2_pair, v3_pool)
        if comparison:
            results.append(comparison)
            logger.info(f"Pair {comparison['pair']}: "
                        f"V2 Price = {comparison['v2_price']:.6f}, "
                        f"V3 Price = {comparison['v3_price']:.6f}, "
                        f"Deviation = {comparison['deviation']:.4%}")
    
    # Sort results by deviation
    results.sort(key=lambda x: x['deviation'], reverse=True)
    
    logger.info("\nTop 10 pairs with highest price deviation:")
    for i, result in enumerate(results[:10], 1):
        logger.info(f"{i}. {result['pair']}: Deviation = {result['deviation']:.4%}")
        logger.info(f"   V2 ({result['v2_key']}): {result['v2_price']:.6f}")
        logger.info(f"   V3 ({result['v3_key']}): {result['v3_price']:.6f}")
        logger.info(f"   Potential arbitrage opportunity: {'Yes' if result['deviation'] > PRICE_DEVIATION_THRESHOLD else 'No'}")
        logger.info("")

    logger.info("Comparison completed.")

if __name__ == "__main__":
    asyncio.run(main())