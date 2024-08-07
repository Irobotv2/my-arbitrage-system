import redis
import json

# Redis connection
redis_client = redis.Redis(host='localhost', port=6379, db=0)

def inspect_redis_data(data_type, sample_size=5):
    if data_type == 'v2':
        pattern = 'uniswap_v2_pairs:*'
    else:
        pattern = 'uniswap_v3_pools:*'
    
    keys = redis_client.keys(pattern)
    print(f"Found {len(keys)} {data_type.upper()} pairs/pools in Redis")
    
    for i, key in enumerate(keys[:sample_size]):
        key_str = key.decode('utf-8')
        data = redis_client.hgetall(key)
        print(f"\nSample {i+1} - Key: {key_str}")
        for field, value in data.items():
            print(f"  {field.decode('utf-8')}: {value.decode('utf-8')}")

    if len(keys) > sample_size:
        print(f"\n... and {len(keys) - sample_size} more.")

print("Inspecting Uniswap V2 pairs:")
inspect_redis_data('v2')

print("\nInspecting Uniswap V3 pools:")
inspect_redis_data('v3')