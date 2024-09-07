from web3 import Web3
from web3.middleware import geth_poa_middleware
import redis
import json

# Configuration
TENDERLY_URL = "https://virtual.mainnet.rpc.tenderly.co/c4e60e60-6398-4e23-9ffc-f48f66d9706e"
web3 = Web3(Web3.HTTPProvider(TENDERLY_URL))
web3.middleware_onion.inject(geth_poa_middleware, layer=0)

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Uniswap V2 Factory address
uniswap_v2_factory = "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"

# FlashBotsUniswapQuery contract address (you need to deploy this contract first)
flashbots_query_address = "YOUR_DEPLOYED_FLASHBOTS_QUERY_CONTRACT_ADDRESS"

# ABIs
factory_abi = [
    {"inputs":[],"name":"allPairsLength","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"internalType":"uint256","name":"","type":"uint256"}],"name":"allPairs","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"}
]

flashbots_query_abi = [
    {"inputs":[{"internalType":"contract UniswapV2Factory","name":"uniswapFactory","type":"address"},{"internalType":"uint256","name":"start","type":"uint256"},{"internalType":"uint256","name":"stop","type":"uint256"}],"name":"getPairsByIndexRange","outputs":[{"internalType":"address[3][]","name":"","type":"address[3][]"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"internalType":"contract IUniswapV2Pair[]","name":"_pairs","type":"address[]"}],"name":"getReservesByPairs","outputs":[{"internalType":"uint256[3][]","name":"","type":"uint256[3][]"}],"stateMutability":"view","type":"function"}
]

# Create contract objects
factory_contract = web3.eth.contract(address=uniswap_v2_factory, abi=factory_abi)
flashbots_query_contract = web3.eth.contract(address=flashbots_query_address, abi=flashbots_query_abi)

def fetch_all_configurations():
    configs = {}
    for key in redis_client.keys('*_config'):
        config_json = redis_client.get(key)
        config = json.loads(config_json)
        configs[key.decode('utf-8')] = config
    return configs

def get_all_pairs():
    pairs_length = factory_contract.functions.allPairsLength().call()
    batch_size = 1000  # Adjust based on your needs
    all_pairs = []

    for start in range(0, pairs_length, batch_size):
        stop = min(start + batch_size, pairs_length)
        pairs_batch = flashbots_query_contract.functions.getPairsByIndexRange(uniswap_v2_factory, start, stop).call()
        all_pairs.extend(pairs_batch)

    return all_pairs

def get_reserves(pairs):
    reserves = flashbots_query_contract.functions.getReservesByPairs(pairs).call()
    return reserves

def calculate_price(reserve0, reserve1, decimals0, decimals1):
    if reserve0 == 0 or reserve1 == 0:
        return 0
    return (reserve1 / 10**decimals1) / (reserve0 / 10**decimals0)

def main():
    configurations = fetch_all_configurations()
    all_pairs = get_all_pairs()

    for config_name, config in configurations.items():
        token0 = web3.to_checksum_address(config['token0']['address'])
        token1 = web3.to_checksum_address(config['token1']['address'])
        decimals0 = int(config['token0'].get('decimals', 18))
        decimals1 = int(config['token1'].get('decimals', 18))

        pair_address = None
        for pair in all_pairs:
            if (pair[0] == token0 and pair[1] == token1) or (pair[0] == token1 and pair[1] == token0):
                pair_address = pair[2]
                break

        if pair_address:
            reserves = get_reserves([pair_address])[0]
            reserve0, reserve1, _ = reserves

            if pair[0] == token1:  # Swap reserves if tokens are in reverse order
                reserve0, reserve1 = reserve1, reserve0

            price = calculate_price(reserve0, reserve1, decimals0, decimals1)

            print(f"\nQuote for {config_name} on Uniswap V2:")
            print(f"Pair address: {pair_address}")
            print(f"Reserve {config['token0']['symbol']}: {reserve0 / 10**decimals0:.6f}")
            print(f"Reserve {config['token1']['symbol']}: {reserve1 / 10**decimals1:.6f}")
            print(f"Price: 1 {config['token0']['symbol']} = {price:.6f} {config['token1']['symbol']}")
            print(f"Uniswap V2 fee: 0.3%")
        else:
            print(f"\nNo Uniswap V2 pair found for {config_name}")

if __name__ == "__main__":
    main()