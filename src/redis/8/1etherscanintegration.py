import redis
import json

# Redis configuration
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_DB = 0

# Initialize Redis connection
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)

def count_keys(pattern):
    """Count keys matching the given pattern."""
    return len(r.keys(pattern))

def get_sample_entries(pattern, num_samples=5):
    """Get a sample of entries matching the pattern."""
    keys = r.keys(pattern)
    samples = keys[:num_samples]
    entries = []
    for key in samples:
        entry = r.hgetall(key)
        entries.append({key.decode(): {k.decode(): v.decode() for k, v in entry.items()}})
    return entries

def main():
    # Count V2 pairs and V3 pools
    v2_count = count_keys("uniswap_v2_pairs:*")
    v3_count = count_keys("uniswap_v3_pools:*")

    print(f"Total Uniswap V2 pairs in Redis: {v2_count}")
    print(f"Total Uniswap V3 pools in Redis: {v3_count}")

    # Get samples
    v2_samples = get_sample_entries("uniswap_v2_pairs:*")
    v3_samples = get_sample_entries("uniswap_v3_pools:*")

    print("\nSample Uniswap V2 pairs:")
    print(json.dumps(v2_samples, indent=2))

    print("\nSample Uniswap V3 pools:")
    print(json.dumps(v3_samples, indent=2))

    # Option to view specific entry
    while True:
        address = input("\nEnter a pair/pool address to view details (or 'q' to quit): ")
        if address.lower() == 'q':
            break
        
        v2_key = f"uniswap_v2_pairs:{address}"
        v3_key = f"uniswap_v3_pools:{address}"
        
        if r.exists(v2_key):
            entry = r.hgetall(v2_key)
            print("Uniswap V2 Pair:")
            print(json.dumps({k.decode(): v.decode() for k, v in entry.items()}, indent=2))
        elif r.exists(v3_key):
            entry = r.hgetall(v3_key)
            print("Uniswap V3 Pool:")
            print(json.dumps({k.decode(): v.decode() for k, v in entry.items()}, indent=2))
        else:
            print("Address not found in Redis.")

if __name__ == "__main__":
    main()