import redis
from decimal import Decimal
from web3 import Web3
import json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ABI of the FlashLoanArbitrage contract
CONTRACT_ABI = json.loads('[{"inputs":[],"stateMutability":"nonpayable","type":"constructor"},{"anonymous":false,"inputs":[{"indexed":false,"internalType":"uint256","name":"profit","type":"uint256"}],"name":"ArbitrageExecuted","type":"event"},{"anonymous":false,"inputs":[{"indexed":false,"internalType":"uint256","name":"flashLoanAmount","type":"uint256"},{"indexed":false,"internalType":"uint256","name":"finalAmount","type":"uint256"},{"indexed":false,"internalType":"uint256","name":"profit","type":"uint256"}],"name":"SimulationComplete","type":"event"},{"anonymous":false,"inputs":[{"indexed":false,"internalType":"string","name":"message","type":"string"}],"name":"SimulationError","type":"event"},{"inputs":[{"internalType":"uint256","name":"flashLoanAmount","type":"uint256"},{"components":[{"internalType":"address","name":"tokenIn","type":"address"},{"internalType":"address","name":"tokenOut","type":"address"},{"internalType":"address","name":"pool","type":"address"},{"internalType":"bool","name":"isV3","type":"bool"},{"internalType":"uint24","name":"fee","type":"uint24"},{"internalType":"uint256","name":"price","type":"uint256"}],"internalType":"struct FlashLoanArbitrage.SwapStep[]","name":"path","type":"tuple[]"}],"name":"executeArbitrage","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"owner","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"contract IERC20[]","name":"tokens","type":"address[]"},{"internalType":"uint256[]","name":"amounts","type":"uint256[]"},{"internalType":"uint256[]","name":"feeAmounts","type":"uint256[]"},{"internalType":"bytes","name":"userData","type":"bytes"}],"name":"receiveFlashLoan","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"components":[{"internalType":"address","name":"tokenIn","type":"address"},{"internalType":"address","name":"tokenOut","type":"address"},{"internalType":"address","name":"pool","type":"address"},{"internalType":"bool","name":"isV3","type":"bool"},{"internalType":"uint24","name":"fee","type":"uint24"},{"internalType":"uint256","name":"price","type":"uint256"}],"internalType":"struct FlashLoanArbitrage.SwapStep[]","name":"path","type":"tuple[]"},{"internalType":"uint256","name":"flashLoanAmount","type":"uint256"}],"name":"simulateArbitrage","outputs":[{"internalType":"uint256","name":"estimatedProfit","type":"uint256"},{"internalType":"uint256[]","name":"simulationResults","type":"uint256[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"price","type":"uint256"}],"name":"simulateV2Swap","outputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"}],"stateMutability":"pure","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint24","name":"fee","type":"uint24"},{"internalType":"uint256","name":"price","type":"uint256"}],"name":"simulateV3Swap","outputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"}],"stateMutability":"pure","type":"function"},{"inputs":[{"internalType":"int256","name":"amount0Delta","type":"int256"},{"internalType":"int256","name":"amount1Delta","type":"int256"},{"internalType":"bytes","name":"data","type":"bytes"}],"name":"uniswapV3SwapCallback","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"withdraw","outputs":[],"stateMutability":"nonpayable","type":"function"},{"stateMutability":"payable","type":"receive"}]')
CONTRACT_ADDRESS = Web3.to_checksum_address('0xb7ae06bb6d128124f76a5c812591ff6c27e5d15b')

class Graph:
    def __init__(self):
        self.edges = {}

    def add_edge(self, from_token, to_token, pool, is_v3, fee, price):
        if from_token not in self.edges:
            self.edges[from_token] = []
        self.edges[from_token].append((to_token, pool, is_v3, fee, price))

def fetch_pool_data_from_redis():
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        v2_pairs = {}
        v3_pools = {}
        for key in r.scan_iter("uniswap_v2_pairs:*"):
            if r.type(key) == b'hash':
                pair_data = r.hgetall(key)
                v2_pairs[key.decode()] = {k.decode(): v.decode() for k, v in pair_data.items()}
        for key in r.scan_iter("uniswap_v3_pools:*"):
            if r.type(key) == b'hash':
                pool_data = r.hgetall(key)
                v3_pools[key.decode()] = {k.decode(): v.decode() for k, v in pool_data.items()}
        
        logger.info(f"Fetched {len(v2_pairs)} V2 pairs and {len(v3_pools)} V3 pools from Redis")
        
        # Log a sample of the data
        if v2_pairs:
            sample_v2 = next(iter(v2_pairs.items()))
            logger.info(f"Sample V2 pair data: {sample_v2}")
        if v3_pools:
            sample_v3 = next(iter(v3_pools.items()))
            logger.info(f"Sample V3 pool data: {sample_v3}")
        
        return v2_pairs, v3_pools
    except redis.RedisError as e:
        logger.error(f"Error fetching data from Redis: {e}")
        return {}, {}
def build_graph(v2_pairs, v3_pools):
    graph = Graph()
    v2_complete = 0
    v3_complete = 0
    
    for key, pair_data in v2_pairs.items():
        try:
            token0 = pair_data.get('token0')
            token1 = pair_data.get('token1')
            reserve0 = Decimal(pair_data.get('reserve0', '0'))
            reserve1 = Decimal(pair_data.get('reserve1', '0'))
            if token0 and token1 and reserve0 and reserve1:
                price0 = reserve1 / reserve0
                price1 = reserve0 / reserve1
                graph.add_edge(token0, token1, pair_data.get('address', ''), False, Decimal('0.003'), price0)
                graph.add_edge(token1, token0, pair_data.get('address', ''), False, Decimal('0.003'), price1)
                v2_complete += 1
            else:
                logger.warning(f"Incomplete data for V2 pair {key}: {pair_data}")
        except Exception as e:
            logger.error(f"Error processing V2 pair {key}: {e}")

    for key, pool_data in v3_pools.items():
        try:
            token0 = pool_data.get('token0')
            token1 = pool_data.get('token1')
            sqrtPriceX96 = Decimal(pool_data.get('sqrtPriceX96', '0'))
            fee = Decimal(pool_data.get('fee', '0')) / Decimal('1000000')
            if token0 and token1 and sqrtPriceX96:
                price = (sqrtPriceX96 / Decimal(2**96)) ** 2
                graph.add_edge(token0, token1, pool_data.get('address', ''), True, fee, price)
                graph.add_edge(token1, token0, pool_data.get('address', ''), True, fee, 1/price)
                v3_complete += 1
            else:
                logger.warning(f"Incomplete data for V3 pool {key}: {pool_data}")
        except Exception as e:
            logger.error(f"Error processing V3 pool {key}: {e}")

    logger.info(f"Built graph with {len(graph.edges)} tokens")
    logger.info(f"Complete V2 pairs: {v2_complete}/{len(v2_pairs)}")
    logger.info(f"Complete V3 pools: {v3_complete}/{len(v3_pools)}")
    return graph

def find_arbitrage_paths(graph, start_token, max_depth=3):
    paths = []
    stack = [(start_token, [start_token], Decimal('1'))]
    
    while stack:
        current_token, path, cumulative_rate = stack.pop()
        
        if len(path) > 1 and current_token == start_token:
            if cumulative_rate > Decimal('1'):
                paths.append((path, cumulative_rate))
        
        if len(path) <= max_depth:
            for neighbor, pool, is_v3, fee, price in graph.edges.get(current_token, []):
                if neighbor not in path or neighbor == start_token:
                    new_rate = cumulative_rate * price * (1 - fee)
                    stack.append((neighbor, path + [neighbor], new_rate))
    
    logger.info(f"Found {len(paths)} arbitrage paths for {start_token}")
    return paths

def prepare_swap_steps(path, graph):
    swap_steps = []
    for i in range(len(path) - 1):
        from_token = path[i]
        to_token = path[i+1]
        for edge in graph.edges.get(from_token, []):
            if edge[0] == to_token:
                swap_steps.append({
                    'tokenIn': from_token,
                    'tokenOut': to_token,
                    'pool': edge[1],
                    'isV3': edge[2],
                    'fee': int(edge[3] * Decimal('1e6')),
                    'price': int(edge[4] * Decimal('1e18'))
                })
                break
    return swap_steps

def simulate_arbitrage(web3, contract, swap_steps, flash_loan_amount):
    try:
        contract_function = contract.functions.simulateArbitrage(swap_steps, flash_loan_amount)
        return contract_function.call()
    except Exception as e:
        logger.error(f"Error simulating arbitrage: {e}")
        return 0, []

def main():
    # Use WebSocket provider instead of HTTP
    web3 = Web3(Web3.WebsocketProvider('wss://mainnet.infura.io/ws/v3/0640f56f05a942d7a25cfeff50de344d'))
    if not web3.is_connected():
        logger.error("Failed to connect to Ethereum network")
        return

    contract = web3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)

    v2_pairs, v3_pools = fetch_pool_data_from_redis()
    if not v2_pairs and not v3_pools:
        logger.error("No pool data fetched from Redis")
        return

    graph = build_graph(v2_pairs, v3_pools)
    if not graph.edges:
        logger.error("Graph is empty. No arbitrage opportunities can be found.")
        return

    start_tokens = [
        "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
        "0x6B175474E89094C44Da98b954EedeAC495271d0F",  # DAI
    ]
    
    all_paths = []
    for start_token in start_tokens:
        all_paths.extend(find_arbitrage_paths(graph, start_token))
    
    # Sort paths by profitability
    all_paths.sort(key=lambda x: x[1], reverse=True)
    
    logger.info(f"Simulating top 10 arbitrage opportunities")
    # Simulate top 10 opportunities
    for path, profit in all_paths[:10]:
        swap_steps = prepare_swap_steps(path, graph)
        flash_loan_amount = int(1e18)  # 1 ETH
        estimated_profit, simulation_results = simulate_arbitrage(web3, contract, swap_steps, flash_loan_amount)
        logger.info(f"Path: {' -> '.join(path)}")
        logger.info(f"Estimated profit: {estimated_profit / 1e18} ETH")
        logger.info(f"Simulation results: {[result / 1e18 for result in simulation_results]}")
        logger.info("")

if __name__ == "__main__":
    main()

# Test cases
import unittest
from unittest.mock import patch, MagicMock

class TestArbitrageFinder(unittest.TestCase):
    def setUp(self):
        self.graph = Graph()
        self.graph.add_edge("WETH", "USDC", "0x1", False, Decimal('0.003'), Decimal('2000'))
        self.graph.add_edge("USDC", "WETH", "0x1", False, Decimal('0.003'), Decimal('0.0005'))
        self.graph.add_edge("WETH", "DAI", "0x2", True, Decimal('0.001'), Decimal('2000'))
        self.graph.add_edge("DAI", "WETH", "0x2", True, Decimal('0.001'), Decimal('0.0005'))
        self.graph.add_edge("USDC", "DAI", "0x3", False, Decimal('0.003'), Decimal('1'))
        self.graph.add_edge("DAI", "USDC", "0x3", False, Decimal('0.003'), Decimal('1'))

    def test_find_arbitrage_paths(self):
        paths = find_arbitrage_paths(self.graph, "WETH", max_depth=3)
        self.assertTrue(any(path[0] == ["WETH", "USDC", "DAI", "WETH"] for path in paths))
        self.assertTrue(all(path[1] > 1 for path in paths))

    def test_prepare_swap_steps(self):
        path = ["WETH", "USDC", "DAI", "WETH"]
        swap_steps = prepare_swap_steps(path, self.graph)
        self.assertEqual(len(swap_steps), 3)
        self.assertEqual(swap_steps[0]['tokenIn'], "WETH")
        self.assertEqual(swap_steps[0]['tokenOut'], "USDC")
        self.assertEqual(swap_steps[0]['isV3'], False)

    @patch('web3.eth.Contract')
    def test_simulate_arbitrage(self, mock_contract):
        mock_contract.functions.simulateArbitrage.return_value.call.return_value = (int(1e15), [int(1e18), int(2e18), int(1.9e18), int(1.01e18)])
        web3 = MagicMock()
        swap_steps = [{'tokenIn': 'WETH', 'tokenOut': 'USDC', 'pool': '0x1', 'isV3': False, 'fee': 3000, 'price': int(2000e18)}]
        flash_loan_amount = int(1e18)
        estimated_profit, simulation_results = simulate_arbitrage(web3, mock_contract, swap_steps, flash_loan_amount)
        self.assertEqual(estimated_profit, int(1e15))
        self.assertEqual(len(simulation_results), 4)

if __name__ == '__main__':
    unittest.main()