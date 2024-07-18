import asyncio
import aiohttp
from web3 import AsyncWeb3
import aiomysql
from decimal import Decimal

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'arbitrage_user',
    'password': 'Newpassword1!',
    'db': 'arbitrage_system',
    'maxsize': 5,
    'minsize': 1,
}

# Tenderly RPC URL
TENDERLY_RPC_URL = 'https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c'

# Contract addresses and ABIs (simplified)
UNI_V2_PAIR_ADDRESS = '0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc'
UNI_V3_POOL_ADDRESS = '0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8'
UNI_V2_ABI = [{"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"stateMutability":"view","type":"function"}]
UNI_V3_ABI = [{"inputs":[],"name":"slot0","outputs":[{"internalType":"uint160","name":"sqrtPriceX96","type":"uint160"},{"internalType":"int24","name":"tick","type":"int24"},{"internalType":"uint16","name":"observationIndex","type":"uint16"},{"internalType":"uint16","name":"observationCardinality","type":"uint16"},{"internalType":"uint16","name":"observationCardinalityNext","type":"uint16"},{"internalType":"uint8","name":"feeProtocol","type":"uint8"},{"internalType":"bool","name":"unlocked","type":"bool"}],"stateMutability":"view","type":"function"}]

web3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(TENDERLY_RPC_URL))
async def fetch_uniswap_v2_data():
    contract = web3.eth.contract(address=UNI_V2_PAIR_ADDRESS, abi=UNI_V2_ABI)
    reserves = await contract.functions.getReserves().call()
    print(f"V2 Reserves: {reserves[0]}, {reserves[1]}")  # Debug print
    return reserves[0], reserves[1]

async def fetch_uniswap_v3_data():
    contract = web3.eth.contract(address=UNI_V3_POOL_ADDRESS, abi=UNI_V3_ABI)
    slot0 = await contract.functions.slot0().call()
    print(f"V3 Slot0: {slot0}")  # Debug print
    return slot0[0], slot0[1]

async def update_pair_data(pool):
    v2_reserves, v3_data = await asyncio.gather(
        fetch_uniswap_v2_data(),
        fetch_uniswap_v3_data()
    )
    
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                UPDATE uniswap_v2_pairs 
                SET reserve0 = %s, reserve1 = %s, last_sync = NOW() 
                WHERE pair_address = %s
            """, (str(v2_reserves[0]), str(v2_reserves[1]), UNI_V2_PAIR_ADDRESS))
            
            await cur.execute("""
                UPDATE uniswap_v3_pools 
                SET sqrt_price = %s, current_tick = %s 
                WHERE pool_address = %s
            """, (str(v3_data[0]), v3_data[1], UNI_V3_POOL_ADDRESS))
            
        await conn.commit()
    
    print("Database updated with new values")  # Debug print

async def check_arbitrage_opportunity(pool):
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT 
                  v2.pair_address AS v2_pair,
                  v3.pool_address AS v3_pool,
                  v2.token0_address,
                  v2.token1_address,
                  v2.reserve1 / v2.reserve0 AS v2_price,
                  (CAST(v3.sqrt_price AS DECIMAL(65,0)) * CAST(v3.sqrt_price AS DECIMAL(65,0))) / POW(2, 192) AS v3_price
                FROM uniswap_v2_pairs v2
                JOIN uniswap_v3_pools v3 ON v2.token0_address = v3.token0_address AND v2.token1_address = v3.token1_address
                WHERE ABS(v2.reserve1 / v2.reserve0 - (CAST(v3.sqrt_price AS DECIMAL(65,0)) * CAST(v3.sqrt_price AS DECIMAL(65,0))) / POW(2, 192)) / (v2.reserve1 / v2.reserve0) > 0.01
            """)
            opportunities = await cur.fetchall()
    
    if not opportunities:
        print("No arbitrage opportunities found")  # Debug print
    
    for opp in opportunities:
        print(f"Arbitrage opportunity found:")
        print(f"V2 Pair: {opp[0]}, V3 Pool: {opp[1]}")
        print(f"Token0: {opp[2]}, Token1: {opp[3]}")
        print(f"V2 Price: {opp[4]}, V3 Price: {opp[5]}")
        print(f"Price Difference: {abs(Decimal(opp[4]) - Decimal(opp[5])) / Decimal(opp[4]) * 100}%")
        print("---")

async def main():
    pool = await aiomysql.create_pool(**DB_CONFIG)
    
    while True:
        try:
            await update_pair_data(pool)
            await check_arbitrage_opportunity(pool)
        except Exception as e:
            print(f"An error occurred: {e}")
        await asyncio.sleep(1)  # Check every second

if __name__ == "__main__":
    asyncio.run(main())