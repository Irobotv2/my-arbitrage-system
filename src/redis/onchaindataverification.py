from web3 import Web3
import json

# Initialize Web3
w3 = Web3(Web3.HTTPProvider('http://localhost:8545'))

# ABIs
UNISWAP_V2_FACTORY_ABI = json.loads('[{"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"}],"name":"getPair","outputs":[{"internalType":"address","name":"pair","type":"address"}],"stateMutability":"view","type":"function"}]')
UNISWAP_V3_FACTORY_ABI = json.loads('[{"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"},{"internalType":"uint24","name":"fee","type":"uint24"}],"name":"getPool","outputs":[{"internalType":"address","name":"pool","type":"address"}],"stateMutability":"view","type":"function"}]')

UNISWAP_V2_FACTORY = "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"
UNISWAP_V3_FACTORY = "0x1F98431c8aD98523631AE4a59f267346ea31F984"

def get_v2_pair(token0, token1):
    factory_contract = w3.eth.contract(address=UNISWAP_V2_FACTORY, abi=UNISWAP_V2_FACTORY_ABI)
    pair_address = factory_contract.functions.getPair(token0, token1).call()
    return pair_address

def get_v3_pool(token0, token1, fee):
    factory_contract = w3.eth.contract(address=UNISWAP_V3_FACTORY, abi=UNISWAP_V3_FACTORY_ABI)
    pool_address = factory_contract.functions.getPool(token0, token1, fee).call()
    return pool_address

tokens = [
    '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',  # WETH
    '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48',  # USDC
    '0x6B175474E89094C44Da98b954EedeAC495271d0F',  # DAI
]

fee_tiers = [500, 3000, 10000]

for i in range(len(tokens)):
    for j in range(i+1, len(tokens)):
        print(f"\nChecking pair: {tokens[i]} - {tokens[j]}")
        v2_pair = get_v2_pair(tokens[i], tokens[j])
        print(f"Uniswap V2 Pair: {v2_pair}")
        
        for fee in fee_tiers:
            v3_pool = get_v3_pool(tokens[i], tokens[j], fee)
            print(f"Uniswap V3 Pool (fee {fee}): {v3_pool}")