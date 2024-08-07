import redis
import json

r = redis.Redis(host='localhost', port=6379, db=0)

def get_all_pools():
    v2_pairs = {}
    v3_pools = {}
    
    for key in r.scan_iter("uniswap_v2_pairs:*"):
        key_type = r.type(key).decode()
        if key_type == 'hash':
            pair_data = r.hgetall(key)
            v2_pairs[key.decode()] = {k.decode(): v.decode() for k, v in pair_data.items()}
        else:
            print(f"Skipping unexpected type for key {key.decode()}: {key_type}")

    for key in r.scan_iter("uniswap_v3_pools:*"):
        key_type = r.type(key).decode()
        if key_type == 'hash':
            pool_data = r.hgetall(key)
            v3_pools[key.decode()] = {k.decode(): v.decode() for k, v in pool_data.items()}
        elif key_type == 'set':
            # Handle set type differently, if needed
            set_members = r.smembers(key)
            v3_pools[key.decode()] = [member.decode() for member in set_members]
        else:
            print(f"Skipping unexpected type for key {key.decode()}: {key_type}")

    return v2_pairs, v3_pools

v2_pairs, v3_pools = get_all_pools()

print(f"\nRetrieved {len(v2_pairs)} V2 pairs and {len(v3_pools)} V3 pools")