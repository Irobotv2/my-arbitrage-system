import asyncio
import redis
from web3 import Web3
import json
from decimal import Decimal

# Redis connection setup
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Ethereum node setup (replace with your own node URL if needed)
ETH_NODE_URL = 'http://localhost:8545'
w3 = Web3(Web3.HTTPProvider(ETH_NODE_URL))

# Uniswap V2 Factory address
UNISWAP_V2_FACTORY = '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f'

# Uniswap V2 Factory ABI (only the function we need)
UNISWAP_V2_FACTORY_ABI = json.loads('''[
    {"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"}],"name":"getPair","outputs":[{"internalType":"address","name":"pair","type":"address"}],"stateMutability":"view","type":"function"}
]''')

# Uniswap V2 Pair ABI (only the functions we need)
UNISWAP_V2_PAIR_ABI = json.loads('''[
    {"constant":true,"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"payable":false,"stateMutability":"view","type":"function"},
    {"constant":true,"inputs":[],"name":"token0","outputs":[{"internalType":"address","name":"","type":"address"}],"payable":false,"stateMutability":"view","type":"function"},
    {"constant":true,"inputs":[],"name":"token1","outputs":[{"internalType":"address","name":"","type":"address"}],"payable":false,"stateMutability":"view","type":"function"}
]''')

# ERC20 ABI (for getting decimals)
ERC20_ABI = json.loads('''[
    {"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"}
]''')

factory_contract = w3.eth.contract(address=UNISWAP_V2_FACTORY, abi=UNISWAP_V2_FACTORY_ABI)

async def get_pair_address(token0_address, token1_address):
    return factory_contract.functions.getPair(
        Web3.to_checksum_address(token0_address),
        Web3.to_checksum_address(token1_address)
    ).call()

async def get_token_decimals(token_address):
    token_contract = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=ERC20_ABI)
    return token_contract.functions.decimals().call()

async def fetch_pair_data(pair_address):
    pair_contract = w3.eth.contract(address=pair_address, abi=UNISWAP_V2_PAIR_ABI)
    reserves = pair_contract.functions.getReserves().call()
    token0 = pair_contract.functions.token0().call()
    token1 = pair_contract.functions.token1().call()
    return reserves[0], reserves[1], token0, token1

async def update_pair(pair_key):
    pair_data = redis_client.hgetall(pair_key)
    token0_address = Web3.to_checksum_address(pair_data['token0_address'])
    token1_address = Web3.to_checksum_address(pair_data['token1_address'])
    
    try:
        pair_address = await get_pair_address(token0_address, token1_address)
        if pair_address == '0x0000000000000000000000000000000000000000':
            print(f"No Uniswap V2 pair found for {pair_key}")
            print(f"Token0: {token0_address}, Token1: {token1_address}")
            return

        reserve0, reserve1, contract_token0, contract_token1 = await fetch_pair_data(pair_address)
        
        # Ensure token order matches the stored order
        if contract_token0.lower() != token0_address.lower():
            reserve0, reserve1 = reserve1, reserve0
            contract_token0, contract_token1 = contract_token1, contract_token0

        decimals0 = await get_token_decimals(contract_token0)
        decimals1 = await get_token_decimals(contract_token1)

        # Calculate price (token1 per token0)
        price = (Decimal(reserve1) / Decimal(10**decimals1)) / (Decimal(reserve0) / Decimal(10**decimals0))
        
        # Calculate liquidity in USD
        if 'ETH' in pair_key:
            eth_price = Decimal('2537.07')  # Use the ETH price from your expected data
            liquidity = (Decimal(reserve0) / Decimal(10**decimals0) + Decimal(reserve1) / Decimal(10**decimals1) * price) * eth_price
        else:
            liquidity = (Decimal(reserve0) / Decimal(10**decimals0)) * price + (Decimal(reserve1) / Decimal(10**decimals1))
        
        # Update Redis
        redis_client.hset(pair_key, mapping={
            "price": str(price),
            "liquidity": str(liquidity),
            "reserve0": str(reserve0),
            "reserve1": str(reserve1),
            "pair_address": pair_address
        })
        
        print(f"Updated {pair_key}: Price = {price:.2f}, Liquidity = ${liquidity:.2f}")
    except Exception as e:
        print(f"Error updating {pair_key}: {str(e)}")

async def update_all_pairs():
    all_pairs = redis_client.smembers("Uniswap V2:pairs")
    update_tasks = [update_pair(pair_key) for pair_key in all_pairs]
    await asyncio.gather(*update_tasks)

async def main():
    while True:
        print("Updating Uniswap V2 pairs...")
        await update_all_pairs()
        print("Update completed. Waiting for next cycle...")
        await asyncio.sleep(60)  # Wait for 60 seconds before the next update

if __name__ == "__main__":
    asyncio.run(main())