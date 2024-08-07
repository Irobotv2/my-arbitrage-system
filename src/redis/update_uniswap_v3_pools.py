import requests
import json
import redis
from decimal import Decimal

# API configuration
API_KEY = "bde86d5008a99eaf066b94e4cfcad7fc"
BASE_URL = "https://gateway-arbitrum.network.thegraph.com/api"
SUBGRAPH_ID = "Dki5NV9qnFsg6cLpUH8rHMuNz1tskkgKw94ercyuo1ws"

# Redis configuration
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_DB = 0

# GraphQL query
query = """
{
  pools(first: 200, orderBy: totalValueLockedUSD, orderDirection: desc) {
    id
    token0 {
      id
      symbol
    }
    token1 {
      id
      symbol
    }
    feeTier
    sqrtPrice
    liquidity
    token0Price
    token1Price
  }
}
"""

def fetch_top_pools():
    url = f"{BASE_URL}/{API_KEY}/subgraphs/id/{SUBGRAPH_ID}"
    response = requests.post(url, json={'query': query})
    if response.status_code == 200:
        return response.json()['data']['pools']
    else:
        raise Exception(f"Query failed with status code {response.status_code}")

def update_redis(pools):
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
    for pool in pools:
        key = f"uniswap_v3_pools:{pool['id']}"
        data = {
            'token0_address': pool['token0']['id'],
            'token1_address': pool['token1']['id'],
            'token0_symbol': pool['token0']['symbol'],
            'token1_symbol': pool['token1']['symbol'],
            'sqrt_price': pool['sqrtPrice'],
            'fee_tier': pool['feeTier'],
            'pool_address': pool['id'],
            'liquidity': pool['liquidity'],
            'token0_price': pool['token0Price'],
            'token1_price': pool['token1Price']
        }
        r.hset(key, mapping=data)  # Use hset with mapping parameter instead of hmset
    print(f"Updated {len(pools)} pools in Redis")

def main():
    try:
        pools = fetch_top_pools()
        update_redis(pools)
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()