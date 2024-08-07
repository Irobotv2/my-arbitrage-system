import redis

# Redis configuration
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_DB = 0

def query_uniswap_v3_pools():
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
    pools = []
    for key in r.scan_iter("uniswap_v3_pools:*"):
        try:
            pool_data = r.hgetall(key)
            if pool_data:
                pool = {k.decode(): v.decode() for k, v in pool_data.items()}
                required_fields = ['token0_address', 'token1_address', 'pool_address', 'fee_tier', 'sqrt_price', 'liquidity', 'token0_price', 'token1_price']
                if all(field in pool and pool[field] for field in required_fields):
                    pools.append(pool)
                else:
                    print(f"Warning: Incomplete data for key {key}")
        except redis.exceptions.ResponseError as e:
            print(f"Error retrieving data for key {key}: {str(e)}")
    return pools
def display_pool_info(pool):
    print(f"Pool Address: {pool.get('pool_address', 'N/A')}")
    print(f"Token0: {pool.get('token0_symbol', 'N/A')} ({pool.get('token0_address', 'N/A')})")
    print(f"Token1: {pool.get('token1_symbol', 'N/A')} ({pool.get('token1_address', 'N/A')})")
    print(f"Fee Tier: {pool.get('fee_tier', 'N/A')}")
    print(f"Sqrt Price: {pool.get('sqrt_price', 'N/A')}")
    print(f"Liquidity: {pool.get('liquidity', 'N/A')}")
    print(f"Token0 Price: {pool.get('token0_price', 'N/A')}")
    print(f"Token1 Price: {pool.get('token1_price', 'N/A')}")
    print("---")

def main():
    pools = query_uniswap_v3_pools()
    print(f"Total pools: {len(pools)}")
    print("Displaying info for the first 5 pools:")
    for pool in pools[:5]:
        display_pool_info(pool)

if __name__ == "__main__":
    main()