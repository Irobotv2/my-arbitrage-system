import redis

def check_production_database():
    # Connect to the production Redis database (assumed to be db 0)
    r = redis.Redis(host='localhost', port=6379, db=0)

    print("Checking production Redis database (db 0):")

    # Check for Uniswap V2 pairs
    v2_pairs = r.keys('uniswap_v2_pairs:*')
    print(f"Uniswap V2 pairs found: {len(v2_pairs)}")
    if v2_pairs:
        sample_pair = v2_pairs[0].decode('utf-8')
        print(f"Sample V2 pair: {sample_pair}")
        print(f"Fields: {r.hkeys(sample_pair)}")

    # Check for Uniswap V3 pools
    v3_pools = r.keys('uniswap_v3_pools:*')
    print(f"Uniswap V3 pools found: {len(v3_pools)}")
    if v3_pools:
        sample_pool = v3_pools[0].decode('utf-8')
        print(f"Sample V3 pool: {sample_pool}")
        print(f"Fields: {r.hkeys(sample_pool)}")

    # Check for other key types we used in tests
    key_types = ['exchange:', 'liquidity:', 'arb:opportunities', 'gas:price', 'history:exchanges:', 'config:', 'logs:arbitrage:']
    
    for key_type in key_types:
        keys = r.keys(f'{key_type}*')
        print(f"{key_type} keys found: {len(keys)}")
        if keys:
            sample_key = keys[0].decode('utf-8')
            print(f"Sample key: {sample_key}")
            if r.type(sample_key) == b'hash':
                print(f"Fields: {r.hkeys(sample_key)}")
            elif r.type(sample_key) == b'zset':
                print(f"Members: {r.zrange(sample_key, 0, -1, withscores=True)}")
            elif r.type(sample_key) == b'list':
                print(f"First item: {r.lindex(sample_key, 0)}")
            else:
                print(f"Value: {r.get(sample_key)}")

if __name__ == "__main__":
    check_production_database()