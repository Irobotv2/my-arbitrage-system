import redis
import asyncio

# Redis connection
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

async def get_token_info(token_address):
    token_key = f"token:{token_address}"
    return redis_client.hgetall(token_key)

async def get_v2_pairs(token_address):
    all_pairs = redis_client.keys("uniswap_v2_pair:*")
    relevant_pairs = []
    for pair_key in all_pairs:
        pair_data = redis_client.hgetall(pair_key)
        if pair_data['token0'] == token_address or pair_data['token1'] == token_address:
            relevant_pairs.append(pair_data)
    return relevant_pairs

async def get_v3_pools(token_address):
    all_pools = redis_client.keys("uniswap_v3_pool:*")
    relevant_pools = []
    for pool_key in all_pools:
        pool_data = redis_client.hgetall(pool_key)
        if pool_data['token0'] == token_address or pool_data['token1'] == token_address:
            relevant_pools.append(pool_data)
    return relevant_pools

async def main():
    tokens = [
        '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',  # WETH
        '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48',  # USDC
        '0x6B175474E89094C44Da98b954EedeAC495271d0F',  # DAI
    ]

    for token in tokens:
        print(f"\nToken: {token}")
        token_info = await get_token_info(token)
        print(f"Info: {token_info}")
        
        v2_pairs = await get_v2_pairs(token)
        print(f"Uniswap V2 Pairs: {v2_pairs}")
        
        v3_pools = await get_v3_pools(token)
        print(f"Uniswap V3 Pools: {v3_pools}")

asyncio.run(main())