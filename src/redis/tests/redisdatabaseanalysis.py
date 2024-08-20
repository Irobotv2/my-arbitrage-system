import redis
import json
from collections import Counter

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

def analyze_redis_data():
    print("Analyzing Redis Database...")
    
    # Get all keys
    all_keys = redis_client.keys('*')
    print(f"Total number of keys: {len(all_keys)}")
    
    # Analyze key patterns
    key_patterns = Counter([key.split(':')[0] for key in all_keys])
    print("\nKey patterns:")
    for pattern, count in key_patterns.most_common():
        print(f"  {pattern}: {count}")
    
    # Analyze Uniswap V2 and V3 keys
    analyze_uniswap_v2_pairs()
    analyze_uniswap_v3_pools()

def analyze_uniswap_v2_pairs():
    v2_keys = redis_client.keys('Uniswap V2:*')
    print(f"\nFound {len(v2_keys)} Uniswap V2 pairs")
    if v2_keys:
        sample_key = v2_keys[0]
        sample_data = redis_client.hgetall(sample_key)
        print(f"Sample Uniswap V2 pair key: {sample_key}")
        print("Sample data:")
        print(json.dumps(sample_data, indent=2))

def analyze_uniswap_v3_pools():
    v3_keys = redis_client.keys('Uniswap V3:*')
    print(f"\nFound {len(v3_keys)} Uniswap V3 pool keys")
    
    fee_tier_keys = [key for key in v3_keys if 'Fee tier' in key and ':slot0' not in key and ':quote' not in key]
    slot0_keys = [key for key in v3_keys if ':slot0' in key]
    quote_keys = [key for key in v3_keys if ':quote' in key]
    
    print(f"  Pool address keys: {len(fee_tier_keys)}")
    print(f"  Slot0 data keys: {len(slot0_keys)}")
    print(f"  Quote data keys: {len(quote_keys)}")
    
    if fee_tier_keys:
        sample_key = fee_tier_keys[0]
        sample_data = redis_client.get(sample_key)
        print(f"\nSample Uniswap V3 pool address key: {sample_key}")
        print(f"Pool address: {sample_data}")
    
    if slot0_keys:
        sample_key = slot0_keys[0]
        sample_data = redis_client.hgetall(sample_key)
        print(f"\nSample Uniswap V3 slot0 key: {sample_key}")
        print("Sample slot0 data:")
        print(json.dumps(sample_data, indent=2))
    
    if quote_keys:
        sample_key = quote_keys[0]
        sample_data = redis_client.hgetall(sample_key)
        print(f"\nSample Uniswap V3 quote key: {sample_key}")
        print("Sample quote data:")
        print(json.dumps(sample_data, indent=2))

if __name__ == "__main__":
    analyze_redis_data()