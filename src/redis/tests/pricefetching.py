import asyncio
import aiohttp
from decimal import Decimal
from web3 import Web3

w3 = Web3(Web3.HTTPProvider('http://localhost:8545'))

async def get_uniswap_v2_price(session, pool_address):
    PAIR_ABI = [{"constant": True, "inputs": [], "name": "getReserves", "outputs": [{"name": "reserve0", "type": "uint112"}, {"name": "reserve1", "type": "uint112"}, {"name": "blockTimestampLast", "type": "uint32"}], "type": "function"}]
    
    try:
        async with session.post(w3.provider.endpoint_uri, json={
            "jsonrpc": "2.0",
            "method": "eth_call",
            "params": [{
                "to": pool_address,
                "data": w3.eth.contract(abi=PAIR_ABI).encodeABI(fn_name="getReserves")
            }, "latest"],
            "id": 1
        }) as response:
            result = await response.json()
            print(f"V2 Raw Result: {result}")
            if 'error' in result:
                raise Exception(f"RPC error: {result['error']}")
            decoded_result = w3.codec.decode(['uint112', 'uint112', 'uint32'], bytes.fromhex(result['result'][2:]))
        
        reserve0, reserve1, _ = decoded_result
        print(f"V2 Reserves: reserve0={reserve0}, reserve1={reserve1}")
        if reserve0 == 0 or reserve1 == 0:
            raise Exception("One or both reserves are zero")
        # Assuming reserve0 is ETH (18 decimals) and reserve1 is USDT (6 decimals)
        price = (Decimal(reserve1) / Decimal(10**6)) / (Decimal(reserve0) / Decimal(10**18))
        print(f"V2 Calculated Price: {price}")
        return price
    except Exception as e:
        print(f"Error fetching V2 price: {e}")
        return None

async def get_uniswap_v3_price(session, pool_address):
    POOL_ABI = [{"inputs": [], "name": "slot0", "outputs": [{"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"}, {"internalType": "int24", "name": "tick", "type": "int24"}, {"internalType": "uint16", "name": "observationIndex", "type": "uint16"}, {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"}, {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"}, {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"}, {"internalType": "bool", "name": "unlocked", "type": "bool"}], "stateMutability": "view", "type": "function"}]
    
    try:
        async with session.post(w3.provider.endpoint_uri, json={
            "jsonrpc": "2.0",
            "method": "eth_call",
            "params": [{
                "to": pool_address,
                "data": w3.eth.contract(abi=POOL_ABI).encodeABI(fn_name="slot0")
            }, "latest"],
            "id": 1
        }) as response:
            result = await response.json()
            print(f"V3 Raw Result: {result}")
            if 'error' in result:
                raise Exception(f"RPC error: {result['error']}")
            decoded_result = w3.codec.decode(['uint160', 'int24', 'uint16', 'uint16', 'uint16', 'uint8', 'bool'], bytes.fromhex(result['result'][2:]))
        
        sqrt_price_x96 = Decimal(decoded_result[0])
        print(f"V3 sqrt_price_x96: {sqrt_price_x96}")
        if sqrt_price_x96 == 0:
            raise Exception("sqrt_price_x96 is zero")
        # Calculate price for ETH/USDT
        price = (sqrt_price_x96 ** 2) / (2 ** 192)
        price = price * (10 ** 12)  # Adjust for decimals (USDT has 6, ETH has 18)
        print(f"V3 Calculated Price: {price}")
        return price
    except Exception as e:
        print(f"Error fetching V3 price: {e}")
        return None

async def test_price_fetching():
    async with aiohttp.ClientSession() as session:
        v2_pool = "0x0d4a11d5EEaaC28EC3F61d100daF4d40471f1852"  # ETH/USDT V2 pool
        v3_pool = "0x4e68Ccd3E89f51C3074ca5072bbAC773960dFa36"  # ETH/USDT V3 pool

        v2_price = await get_uniswap_v2_price(session, v2_pool)
        v3_price = await get_uniswap_v3_price(session, v3_pool)

        if v2_price:
            print(f"Uniswap V2 ETH/USDT Price: {v2_price:.2f} USDT")
        if v3_price:
            print(f"Uniswap V3 ETH/USDT Price: {v3_price:.2f} USDT")

if __name__ == "__main__":
    print("Starting price fetching test")
    asyncio.run(test_price_fetching())