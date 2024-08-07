import redis
import requests
from decimal import Decimal

# Redis configuration
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_DB = 0

# API configuration
API_KEY = "bde86d5008a99eaf066b94e4cfcad7fc"
UNISWAP_V2_URL = f"https://gateway-arbitrum.network.thegraph.com/api/{API_KEY}/subgraphs/id/2ZXJn1QPvBpS1UVAsSMvqeGm3XvN29GVo75pXafmiNFb"

def fetch_v3_pairs_from_redis():
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
    v3_pairs = []
    for key in r.scan_iter("uniswap_v3_pools:*"):
        try:
            pool_data = r.hgetall(key)
            if pool_data:
                v3_pairs.append({
                    'token0': pool_data[b'token0_address'].decode(),
                    'token1': pool_data[b'token1_address'].decode(),
                })
            else:
                print(f"Warning: Empty data for key {key.decode()}")
        except redis.exceptions.ResponseError as e:
            key_type = r.type(key).decode()
            print(f"Error: Key {key.decode()} is of type {key_type}, not a hash. Error: {e}")
    print(f"Successfully processed {len(v3_pairs)} V3 pairs")
    return v3_pairs

def fetch_v2_pairs(token_pairs):
    query = """
    query ($pairs: [Pair_filter!]!) {
      pairs(where: {or: $pairs}, first: 1000) {
        id
        token0 {
          id
          symbol
        }
        token1 {
          id
          symbol
        }
        reserve0
        reserve1
        reserveUSD
      }
    }
    """
    variables = {
        "pairs": [
            {"token0": pair['token0'].lower(), "token1": pair['token1'].lower()}
            for pair in token_pairs
        ]
    }
    response = requests.post(UNISWAP_V2_URL, json={'query': query, 'variables': variables})
    if response.status_code == 200:
        return response.json()['data']['pairs']
    else:
        print(f"Failed to fetch V2 pairs: {response.text}")
        return []

def update_redis_with_v2_pair(r, pair):
    key = f"uniswap_v2_pairs:{pair['id']}"
    data = {
        'token0_address': pair['token0']['id'],
        'token1_address': pair['token1']['id'],
        'token0_symbol': pair['token0']['symbol'],
        'token1_symbol': pair['token1']['symbol'],
        'reserve0': pair['reserve0'],
        'reserve1': pair['reserve1'],
        'pool_address': pair['id'],
        'total_liquidity_usd': pair['reserveUSD']
    }
    r.hset(key, mapping=data)
    print(f"Updated V2 pair: {pair['id']}")

def main():
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
        
        v3_pairs = fetch_v3_pairs_from_redis()
        print(f"Found {len(v3_pairs)} valid V3 pairs in Redis")

        v2_pairs = fetch_v2_pairs(v3_pairs)
        print(f"Found {len(v2_pairs)} V2 pairs from the subgraph")

        for v2_pair in v2_pairs:
            update_redis_with_v2_pair(r, v2_pair)

        # Verify data in Redis
        v2_pair_count = len(list(r.scan_iter("uniswap_v2_pairs:*")))
        print(f"Total V2 pairs in Redis: {v2_pair_count}")

        # Print a sample pair
        sample_keys = list(r.scan_iter("uniswap_v2_pairs:*"))
        if sample_keys:
            sample_key = sample_keys[0]
            sample_data = r.hgetall(sample_key)
            print("Sample V2 pair data:")
            for k, v in sample_data.items():
                print(f"{k.decode()}: {v.decode()}")
        else:
            print("No V2 pairs found in Redis")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()