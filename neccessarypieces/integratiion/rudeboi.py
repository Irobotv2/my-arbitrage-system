import redis
import json
import logging
import time
from decimal import Decimal
from collections import defaultdict
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct
import requests
from tenacity import retry, stop_after_attempt, wait_exponential
import concurrent.futures
from functools import partial
# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
main_logger = logging.getLogger('main')
data_detection_logger = logging.getLogger('data_detection')
liquidity_vault_logger = logging.getLogger('liquidity_vault')
execution_logger = logging.getLogger('execution')

# File handlers for specific logs
data_detection_file = logging.FileHandler('data_detection.log')
liquidity_vault_file = logging.FileHandler('liquidity_vault.log')
execution_file = logging.FileHandler('execution.log')

data_detection_logger.addHandler(data_detection_file)
liquidity_vault_logger.addHandler(liquidity_vault_file)
execution_logger.addHandler(execution_file)

# Define constants
INFURA_URL = 'http://localhost:8545'
QUOTER_CONTRACT_ADDRESS = '0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6'
UNISWAP_V2_ROUTER_ADDRESS = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
UNISWAP_V3_ROUTER_ADDRESS = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS = "0x26B7B5AB244114ab88578D5C4cD5b096097bf543"  # Replace with your contract address

wallet_address = "0x6f2F4f0210AC805D817d4CD0b9A4D0c29d232E93"
private_key = "6575ac283b8aa1cbd913d2d28557e318048f8e62a5a19a74001988e2f40ab06c"

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Connect to Ethereum
w3 = Web3(Web3.HTTPProvider(INFURA_URL))

# ABIs (Add full ABIs here)
QUOTER_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenIn", "type": "address"},
            {"internalType": "address", "name": "tokenOut", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"},
        ],
        "name": "quoteExactInputSingle",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]

UNISWAP_V2_PAIR_ABI = json.loads('''
[
    {
        "constant": true,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"internalType": "uint112", "name": "_reserve0", "type": "uint112"},
            {"internalType": "uint112", "name": "_reserve1", "type": "uint112"},
            {"internalType": "uint32", "name": "_blockTimestampLast", "type": "uint32"}
        ],
        "payable": false,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": true,
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "payable": false,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": true,
        "inputs": [],
        "name": "token1",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "payable": false,
        "stateMutability": "view",
        "type": "function"
    }
]
''')
UNISWAP_V2_ROUTER_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForTokens",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "nonpayable",
        "type": "function"
    }
    # Add other necessary functions from the Uniswap V2 Router ABI
]

UNISWAP_V3_ROUTER_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "tokenIn", "type": "address"},
                    {"internalType": "address", "name": "tokenOut", "type": "address"},
                    {"internalType": "uint24", "name": "fee", "type": "uint24"},
                    {"internalType": "address", "name": "recipient", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountOutMinimum", "type": "uint256"},
                    {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"}
                ],
                "internalType": "struct ISwapRouter.ExactInputSingleParams",
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "exactInputSingle",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function"
    }
    # Add other necessary functions from the Uniswap V3 Router ABI
]
V3_POOL_ABI = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
            {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
            {"internalType": "bool", "name": "unlocked", "type": "bool"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function"
    }
]
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    }
]
FLASHLOAN_BUNDLE_EXECUTOR_ABI = [
    {
        "inputs": [
            {"internalType": "contract IERC20[]", "name": "tokens", "type": "address[]"},
            {"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"},
            {"internalType": "address[]", "name": "targets", "type": "address[]"},
            {"internalType": "bytes[]", "name": "payloads", "type": "bytes[]"}
        ],
        "name": "initiateFlashLoanAndBundle",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]
# Initialize contracts
quoter_contract = w3.eth.contract(address=w3.to_checksum_address(QUOTER_CONTRACT_ADDRESS), abi=QUOTER_ABI)
v2_router_contract = w3.eth.contract(address=UNISWAP_V2_ROUTER_ADDRESS, abi=UNISWAP_V2_ROUTER_ABI)
v3_router_contract = w3.eth.contract(address=UNISWAP_V3_ROUTER_ADDRESS, abi=UNISWAP_V3_ROUTER_ABI)
flashloan_contract = w3.eth.contract(address=FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS, abi=FLASHLOAN_BUNDLE_EXECUTOR_ABI)
# Token decimals
TOKEN_DECIMALS = {
    '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48': 6,  # USDC
    '0x6b175474e89094c44da98b954eedeac495271d0f': 18, # DAI
    '0xc02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2': 18, # WETH
    '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599': 8,  # WBTC
}

# Liquidity vaults
tokens_and_pools = {
    'WETH': {'address': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', 'pool': '0xDACf5Fa19b1f720111609043ac67A9818262850c'},
    'wstETH': {'address': '0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0', 'pool': '0x3de27EFa2F1AA663Ae5D458857e731c129069F29'},
    'AAVE': {'address': '0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9', 'pool': '0x3de27EFa2F1AA663Ae5D458857e731c129069F29'},
    'BAL': {'address': '0xba100000625a3754423978a60c9317c58a424e3D', 'pool': '0x5c6Ee304399DBdB9C8Ef030aB642B10820DB8F56'},
    'rETH': {'address': '0xae78736Cd615f374D3085123A210448E74Fc6393', 'pool': '0x1E19CF2D73a72Ef1332C882F20534B6519Be0276'},
    'sDAI': {'address': '0x83F20F44975D03b1b09e64809B757c47f942BEeA', 'pool': '0x2191Df821C198600499aA1f0031b1a7514D7A7D9'},
    'osETH': {'address': '0xf1C9acDc66974dFB6dEcB12aA385b9cD01190E38', 'pool': '0xDACf5Fa19b1f720111609043ac67A9818262850c'},
    'GYD': {'address': '0x1FaE95096322828B3Ef2a8617E1026D80549d8cb', 'pool': '0x2191Df821C198600499aA1f0031b1a7514D7A7D9'},
    'USDC': {'address': '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606EB48', 'pool': '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606EB48'},
}
builder_urls = [
    "https://rpc.flashbots.net",  # Flashbots
    "https://rpc.f1b.io",  # f1b.io
    "https://rsync-builder.xyz",  # rsync
    "https://mevshare-rpc.beaverbuild.org",  # beaverbuild.org
    "https://builder0x69.io",  # builder0x69
    "https://rpc.titanbuilder.xyz",  # Titan
    "https://builder.eigenphi.io",  # EigenPhi
    "https://boba-builder.com/searcher/bundle",  # boba-builder
    "https://builder.gmbit.co/rpc",  # Gambit Labs
    "https://rpc.payload.de",  # payload
    "https://rpc.lokibuilder.xyz",  # Loki
    "https://buildai.net",  # BuildAI
    "https://rpc.mevshare.jetbldr.xyz",  # JetBuilder
    "https://flashbots.rpc.tbuilder.xyz",  # tbuilder
    "https://rpc.penguinbuild.org",  # penguinbuild
    "https://rpc.bobthebuilder.xyz",  # bobthebuilder
    "https://rpc.btcs.com",  # BTCS
    "https://rpc-builder.blxrbdn.com"  # bloXroute
]
# Classes
class Token:
    def __init__(self, address, symbol):
        self.address = address
        self.symbol = symbol

class Pool:
    def __init__(self, address, token0, token1, fee, is_v3):
        self.address = address
        self.token0 = token0
        self.token1 = token1
        self.fee = fee
        self.is_v3 = is_v3

class PoolGraph:
    def __init__(self):
        self.tokens = {}
        self.pools = []
        self.edges = defaultdict(lambda: defaultdict(list))

    def add_token(self, token):
        if token.address not in self.tokens:
            self.tokens[token.address] = token

    def add_pool(self, pool):
        self.pools.append(pool)
        self.edges[pool.token0.address][pool.token1.address].append(pool)
        self.edges[pool.token1.address][pool.token0.address].append(pool)

# Data Detection Algorithm
def load_configurations_from_redis():
    data_detection_logger.info("Loading configurations from Redis...")
    graph = PoolGraph()
    
    # Dynamically fetch all keys from Redis
    configuration_keys = [key.decode('utf-8') for key in redis_client.keys('*_config')]

    for config_key in configuration_keys:
        config_json = redis_client.get(config_key)
        if config_json:
            config = json.loads(config_json)
            token0 = Token(config['token0']['address'], config['token0']['symbol'])
            token1 = Token(config['token1']['address'], config['token1']['symbol'])
            graph.add_token(token0)
            graph.add_token(token1)

            if config.get('v2_pool'):
                pool = Pool(config['v2_pool'], token0, token1, 3000, False)
                graph.add_pool(pool)

            for fee_tier, v3_pool_info in config.get('v3_pools', {}).items():
                pool = Pool(v3_pool_info['address'], token0, token1, int(float(fee_tier[:-1]) * 10000), True)
                graph.add_pool(pool)

    data_detection_logger.info(f"Loaded {len(graph.tokens)} tokens and {len(graph.pools)} pools from configurations")
    return graph


def generate_arbitrage_paths(graph):
    paths = []
    for start_token_address in graph.tokens.keys():
        start_token = graph.tokens[start_token_address]
        for first_pool in graph.edges[start_token_address].values():
            for pool1 in first_pool:
                other_token = pool1.token1 if pool1.token0.address == start_token_address else pool1.token0
                for second_pool in graph.edges[other_token.address][start_token_address]:
                    if pool1 != second_pool:
                        path = [
                            (pool1, start_token, other_token),
                            (second_pool, other_token, start_token)
                        ]
                        paths.append(path)
    data_detection_logger.info(f"Generated {len(paths)} potential arbitrage paths")
    return paths

def simulate_mev_competition(path, amount, profit):
    # Convert 0.01 to a Decimal type
    baseline = Decimal('0.01')

    # Simulate probability of winning based on profit and amount
    win_probability = min(1, profit / (amount * baseline))  # Example: 1% of trade amount as baseline

    # Simulate market impact using a Decimal type
    market_impact = amount * Decimal('0.0005')  # Example: 0.05% market impact

    adjusted_profit = profit - market_impact

    return adjusted_profit, win_probability

def simulate_arbitrage_for_path(path, starting_amount):
    data_detection_logger.info(f"Simulating arbitrage for path: {format_path(path)}")
    starting_token = path[0][1]
    decimals_starting_token = get_token_decimals(starting_token.address)
    amount = Decimal(starting_amount) * Decimal(10 ** decimals_starting_token)

    # Estimate gas cost (this is a rough estimate and should be refined)
    estimated_gas = 300000  # Example gas limit
    gas_price = w3.eth.gas_price
    estimated_gas_cost = Decimal(estimated_gas * gas_price) / Decimal(10 ** 18)  # Convert to ETH

    for pool, token_in, token_out in path:
        if not pool.is_v3:
            pair_contract = w3.eth.contract(address=pool.address, abi=UNISWAP_V2_PAIR_ABI)
            amount = calculate_execution_price(amount, token_in.address, token_out.address, pair_contract)
            # Apply Uniswap V2 fee (0.3%)
            amount = amount * Decimal('0.997')
        else:
            amount = get_quote(token_in.address, token_out.address, amount, pool.fee)
            # V3 fee is already accounted for in the quote

        if amount is None:
            data_detection_logger.error(f"Failed to get amount out for swap {token_in.symbol} -> {token_out.symbol}. Aborting path simulation.")
            return None, None, None

    final_amount_hr = Decimal(amount) / Decimal(10 ** decimals_starting_token)
    profit = final_amount_hr - Decimal(starting_amount) - estimated_gas_cost
    profit_percentage = (profit / Decimal(starting_amount)) * Decimal(100)

    # Adjust profit to account for MEV competition and other factors
    adjusted_profit, win_probability = simulate_mev_competition(path, starting_amount, profit)

    data_detection_logger.info(f"Adjusted Profit: {adjusted_profit:.6f} {starting_token.symbol}")
    data_detection_logger.info(f"Win Probability: {win_probability:.2%}")

    return adjusted_profit, profit_percentage, win_probability



def find_optimal_amount_for_arbitrage(path, min_amount, max_amount, step_size):
    data_detection_logger.info(f"Finding optimal amount for arbitrage path: {format_path(path)}")
    optimal_amount = min_amount
    max_profit = float('-inf')

    for amount in range(min_amount, max_amount + 1, step_size):
        data_detection_logger.info(f"Simulating with input amount: {amount}")
        profit, profit_percentage, win_probability = simulate_arbitrage_for_path(path, amount)

        if profit is not None and profit > max_profit:
            max_profit = profit
            optimal_amount = amount

    data_detection_logger.info(f"Optimal amount: {optimal_amount} with maximum profit: {max_profit:.6f}")
    return optimal_amount, max_profit
# Liquidity Vaults Functions
def get_token_decimals(token_address):
    return TOKEN_DECIMALS.get(token_address.lower(), 18)

def get_initial_token_for_path(path):
    initial_token = path[0][1]
    liquidity_vault_logger.info(f"Attempting to get initial token {initial_token.symbol} for path")
    if initial_token.symbol in tokens_and_pools:
        return tokens_and_pools[initial_token.symbol]
    else:
        liquidity_vault_logger.error(f"Initial token {initial_token.symbol} to run the path is not found in tokens_and_pools function")
        return None
def track_failed_transaction(tx_hash, error):
    failed_tx = {
        'tx_hash': tx_hash.hex(),
        'error': str(error),
        'timestamp': int(time.time()),
    }
    redis_client.lpush('failed_transactions', json.dumps(failed_tx))
    execution_logger.error(f"Transaction failed: {failed_tx}")



@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def send_transaction_with_retry(tx, private_key):
    signed_tx = w3.eth.account.sign_transaction(tx, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    return tx_hash

def analyze_execution_results(expected_profit, actual_profit, gas_used, effective_gas_price):
    analysis = {
        'expected_profit': expected_profit,
        'actual_profit': actual_profit,
        'profit_difference': actual_profit - expected_profit,
        'gas_used': gas_used,
        'effective_gas_price': effective_gas_price,
        'gas_cost': gas_used * effective_gas_price,
    }
    
    execution_logger.info("Execution Analysis:")
    for key, value in analysis.items():
        execution_logger.info(f"{key}: {value}")

    # Store analysis in Redis for further study
    redis_client.lpush('execution_analyses', json.dumps(analysis))
    return analysis
def send_bundle(tx_hash, opportunity):
    base_fee = w3.eth.get_block('latest')['baseFeePerGas']
    priority_fee = w3.eth.max_priority_fee

    transaction_bundle = {
        "txs": [tx_hash],
        "blockNumber": w3.eth.block_number + 1,
        "minTimestamp": int(time.time()),
        "maxTimestamp": int(time.time()) + 60,
        "revertingTxHashes": [],
        "stateBlockNumber": w3.eth.block_number,
        "preferences": {
            "fast": True,
            "privacy": True,
        },
        "inclusion": {
            "block": w3.eth.block_number + 1,
            "maxBlock": w3.eth.block_number + 2,
        },
        "pricing": {
            "baseFee": {
                "max": str(base_fee * 2),  # Willing to pay up to 2x current base fee
            },
            "priorityFee": {
                "max": str(priority_fee * 1.5),  # Willing to pay up to 1.5x current priority fee
            },
        },
    }

    # Send the bundle to builders
    send_bundle_to_builders(transaction_bundle)

def process_arbitrage_path(path, min_amount, max_amount, step_size):
    data_detection_logger.info(f"Processing path: {format_path(path)}")
    optimal_amount, expected_profit = find_optimal_amount_for_arbitrage(path, min_amount, max_amount, step_size)
    
    if expected_profit > 0:
        # Simulate again with the optimal amount to get the win probability
        _, _, win_probability = simulate_arbitrage_for_path(path, optimal_amount)
        opportunity = {
            'path': path,
            'optimal_amount': optimal_amount,
            'expected_profit': expected_profit,
            'win_probability': win_probability
        }
        data_detection_logger.info(f"Profitable opportunity found: {opportunity}")
        log_path_details(path, optimal_amount)
        return opportunity
    return None
# Execution Functions
def execute_arbitrage(opportunity, optimal_amount):
    execution_logger.info(f"Executing arbitrage for opportunity: {opportunity}")
    token0_address = opportunity['token0']['address']
    token1_address = opportunity['token1']['address']
    v3_pool_info = opportunity['v3_pool']
    is_v2_to_v3 = opportunity['direction'] == 'v2_to_v3'

    sorted_tokens = sort_tokens(token0_address, token1_address)

    # Check liquidity for V3 pool
    v3_pool_contract = w3.eth.contract(address=v3_pool_info['address'], abi=V3_POOL_ABI)
    liquidity = v3_pool_contract.functions.liquidity().call()

    if Decimal(liquidity) / Decimal(10 ** 18) < Decimal('0.1'):  # Assuming 0.1 ETH as MIN_LIQUIDITY_THRESHOLD_ETH
        execution_logger.warning(f"V3 pool {v3_pool_info['address']} has insufficient liquidity. Skipping arbitrage execution.")
        return

    flash_loan_amount = w3.to_wei(optimal_amount, 'ether')

    execution_logger.info(f"Executing arbitrage with flash loan amount: {flash_loan_amount} wei")
    execution_logger.info(f"Token0: {token0_address}, Token1: {token1_address}")
    execution_logger.info(f"Sorted tokens: {sorted_tokens}")

    slippage = 0.005  # 0.5% slippage
    min_amount_out = int(flash_loan_amount * (1 - slippage))
    deadline = int(time.time()) + 60 * 2  # 2-minute deadline

    # Prepare approval payloads
    approval_payloads = prepare_approval_payloads(sorted_tokens, flash_loan_amount)

    # Prepare swap payloads
    swap_payloads, swap_targets = prepare_swap_payloads(is_v2_to_v3, sorted_tokens, flash_loan_amount, min_amount_out, deadline, v3_pool_info)

    # Combine all payloads and targets
    all_payloads = approval_payloads + swap_payloads
    all_targets = list(sorted_tokens) + swap_targets

    tokens = list(sorted_tokens)
    amounts = [flash_loan_amount, flash_loan_amount]

    try:
        # Get initial balances
        initial_eth_balance = w3.eth.get_balance(wallet_address)
        initial_token_balances = {
            token: w3.eth.contract(address=token, abi=ERC20_ABI).functions.balanceOf(wallet_address).call()
            for token in sorted_tokens
        }

        nonce = w3.eth.get_transaction_count(wallet_address)
        gas_price = w3.eth.gas_price

        # Estimate gas
        gas_limit = estimate_gas(tokens, amounts, all_targets, all_payloads, nonce)
        estimated_gas_cost = gas_limit * gas_price

        execution_logger.info(f"Estimated gas cost: {w3.from_wei(estimated_gas_cost, 'ether')} ETH")

        tx = build_transaction(tokens, amounts, all_targets, all_payloads, nonce, gas_limit, gas_price)

        # Send transaction with retry
        tx_hash = send_transaction_with_retry(tx, private_key)
        
        # Log submitted transaction
        log_submitted_transaction(tx_hash, opportunity, flash_loan_amount)

        # Prepare and send the transaction bundle
        send_bundle(tx_hash, opportunity)

        # Wait for transaction receipt and log the result
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt['status'] == 1:
            # Transaction successful
            final_eth_balance = w3.eth.get_balance(wallet_address)
            final_token_balances = {
                token: w3.eth.contract(address=token, abi=ERC20_ABI).functions.balanceOf(wallet_address).call()
                for token in sorted_tokens
            }

            actual_gas_cost = receipt['gasUsed'] * receipt['effectiveGasPrice']
            eth_profit = final_eth_balance - initial_eth_balance + actual_gas_cost

            token_profits = {
                token: final_token_balances[token] - initial_token_balances[token]
                for token in sorted_tokens
            }

            execution_logger.info(f"Arbitrage transaction successful - Hash: {tx_hash.hex()}")
            execution_logger.info(f"Actual gas cost: {w3.from_wei(actual_gas_cost, 'ether')} ETH")
            execution_logger.info(f"ETH profit: {w3.from_wei(eth_profit, 'ether')} ETH")
            for token, profit in token_profits.items():
                token_contract = w3.eth.contract(address=token, abi=ERC20_ABI)
                token_symbol = token_contract.functions.symbol().call()
                token_decimals = token_contract.functions.decimals().call()
                profit_formatted = profit / (10 ** token_decimals)
                execution_logger.info(f"{token_symbol} profit: {profit_formatted}")

            # Update profit tracker
            update_profit_tracker(eth_profit, token_profits)

            # Perform post-execution analysis
            expected_profit = opportunity.get('expected_profit', 0)
            actual_profit = eth_profit
            analyze_execution_results(expected_profit, actual_profit, receipt['gasUsed'], receipt['effectiveGasPrice'])

        else:
            execution_logger.error(f"Arbitrage transaction failed - Hash: {tx_hash.hex()}")

    except Exception as e:
        track_failed_transaction(tx_hash, e)


def update_profit_tracker(eth_profit, token_profits):
    try:
        current_profits = json.loads(redis_client.get('total_realized_profits') or '{}')
        
        # Update ETH profit
        current_profits['ETH'] = current_profits.get('ETH', 0) + eth_profit

        # Update token profits
        for token, profit in token_profits.items():
            current_profits[token] = current_profits.get(token, 0) + profit

        redis_client.set('total_realized_profits', json.dumps(current_profits))
        execution_logger.info(f"Updated total realized profits: {current_profits}")
    except Exception as e:
        execution_logger.error(f"Error updating profit tracker: {str(e)}", exc_info=True)

def prepare_approval_payloads(sorted_tokens, flash_loan_amount):
    return [
        w3.eth.contract(address=token, abi=ERC20_ABI).encodeABI(
            fn_name="approve",
            args=[FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS, flash_loan_amount]
        ) for token in sorted_tokens
    ]

def prepare_swap_payloads(is_v2_to_v3, sorted_tokens, flash_loan_amount, min_amount_out, deadline, v3_pool_info):
    if is_v2_to_v3:
        v2_swap_payload = v2_router_contract.encodeABI(
            fn_name="swapExactTokensForTokens",
            args=[flash_loan_amount, min_amount_out, sorted_tokens, FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS, deadline]
        )
        v3_swap_payload = v3_router_contract.encodeABI(
            fn_name="exactInputSingle",
            args=[{
                'tokenIn': sorted_tokens[1], 'tokenOut': sorted_tokens[0], 'fee': v3_pool_info['fee'],
                'recipient': FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS, 'deadline': deadline,
                'amountIn': flash_loan_amount, 'amountOutMinimum': min_amount_out, 'sqrtPriceLimitX96': 0,
            }]
        )
        return [v2_swap_payload, v3_swap_payload], [UNISWAP_V2_ROUTER_ADDRESS, UNISWAP_V3_ROUTER_ADDRESS]
    else:
        v3_swap_payload = v3_router_contract.encodeABI(
            fn_name="exactInputSingle",
            args=[{
                'tokenIn': sorted_tokens[0], 'tokenOut': sorted_tokens[1], 'fee': v3_pool_info['fee'],
                'recipient': FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS, 'deadline': deadline,
                'amountIn': flash_loan_amount, 'amountOutMinimum': min_amount_out, 'sqrtPriceLimitX96': 0,
            }]
        )
        v2_swap_payload = v2_router_contract.encodeABI(
            fn_name="swapExactTokensForTokens",
            args=[flash_loan_amount, min_amount_out, list(reversed(sorted_tokens)), FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS, deadline]
        )
        return [v3_swap_payload, v2_swap_payload], [UNISWAP_V3_ROUTER_ADDRESS, UNISWAP_V2_ROUTER_ADDRESS]

def estimate_gas(tokens, amounts, all_targets, all_payloads, nonce):
    try:
        gas_estimate = flashloan_contract.functions.initiateFlashLoanAndBundle(
            tokens, amounts, all_targets, all_payloads
        ).estimate_gas({'from': wallet_address, 'nonce': nonce})
        return int(gas_estimate * 1.2)  # Add 20% buffer
    except Exception as gas_error:
        execution_logger.warning(f"Gas estimation failed: {str(gas_error)}. Using default gas limit.")
        return 1000000  # Use a higher default gas limit due to complex transaction

def build_transaction(tokens, amounts, all_targets, all_payloads, nonce, gas_limit, gas_price):
    return flashloan_contract.functions.initiateFlashLoanAndBundle(
        tokens, amounts, all_targets, all_payloads
    ).build_transaction({
        'from': wallet_address,
        'nonce': nonce,
        'gas': gas_limit,
        'gasPrice': gas_price,
    })

def log_submitted_transaction(tx_hash, opportunity, flash_loan_amount):
    execution_logger.info(f"Arbitrage transaction submitted - Hash: {tx_hash.hex()}, Pair: {opportunity['name']}, Type: {'V2 to V3' if opportunity['direction'] == 'v2_to_v3' else 'V3 to V2'}, Amount: {flash_loan_amount}, Fee Tier: {opportunity['v3_pool']['fee']}")

def send_bundle(signed_tx, opportunity):
    transaction_bundle = {
        "txs": [signed_tx.rawTransaction.hex()],
        "blockNumber": w3.eth.block_number + 1,
        "minTimestamp": int(time.time()),
        "maxTimestamp": int(time.time()) + 60,  # Bundle valid for the next 60 seconds
        "revertingTxHashes": []
    }
    execution_logger.info(f"Transaction bundle details: {json.dumps(transaction_bundle, indent=2)}")
    send_bundle_to_builders(transaction_bundle)

def log_transaction_result(receipt, tx_hash, opportunity, flash_loan_amount):
    if receipt['status'] == 1:
        execution_logger.info(f"Arbitrage transaction confirmed - Hash: {tx_hash.hex()}, Pair: {opportunity['name']}, Type: {'V2 to V3' if opportunity['direction'] == 'v2_to_v3' else 'V3 to V2'}, Amount: {flash_loan_amount}, Fee Tier: {opportunity['v3_pool']['fee']}, Gas Used: {receipt['gasUsed']}, Effective Gas Price: {receipt['effectiveGasPrice']}")
    else:
        execution_logger.error(f"Arbitrage transaction failed - Hash: {tx_hash.hex()}")

def handle_transaction_error(error):
    error_message = str(error)
    if "execution reverted" in error_message:
        error_data = error_message.split("execution reverted:")[-1].strip()
        decoded_error = decode_balancer_error(error_data)
        execution_logger.error(f"Execution reverted: {decoded_error}")
    elif "SafeMath: subtraction overflow" in error_message:
        execution_logger.error(f"Insufficient token balance: {error_message}")
    elif "UniswapV2Library: INSUFFICIENT_INPUT_AMOUNT" in error_message:
        execution_logger.error(f"Insufficient input amount: {error_message}")
    else:
        execution_logger.error(f"Error executing flashloan arbitrage: {error_message}", exc_info=True)

def send_bundle_to_builders(bundle):
    bundle_json = json.dumps(bundle, separators=(',', ':'))
    message = encode_defunct(text=bundle_json)
    signed_message = Account.sign_message(message, private_key=private_key)
    flashbots_signature = f"{wallet_address}:{signed_message.signature.hex()}"

    headers = {
        "Content-Type": "application/json",
        "X-Flashbots-Signature": flashbots_signature
    }

    for url in builder_urls:
        try:
            execution_logger.info(f"Sending bundle to {url}")
            response = requests.post(url, json=bundle, headers=headers)

            if response.status_code == 200:
                execution_logger.info(f"Bundle sent successfully to {url}: {response.json()}")
            else:
                execution_logger.warning(f"Failed to send bundle to {url}: {response.status_code} - {response.text}")
        except Exception as e:
            execution_logger.error(f"Error sending bundle to {url}: {str(e)}")


# Utility Functions
def sort_tokens(token0, token1):
    return sorted([token0, token1])

def format_path(path):
    result = ["Path:"]
    for i, (pool, token_in, token_out) in enumerate(path, 1):
        pool_type = "V2" if not pool.is_v3 else f"V3/{pool.fee/10000:.2f}%"
        result.append(f"{i}: {token_in.symbol} -> {token_out.symbol} ({pool_type})")
    return "\n".join(result)


def get_quote(token_in, token_out, amount_in, fee_tier):
    try:
        amount_out = quoter_contract.functions.quoteExactInputSingle(
            token_in,
            token_out,
            fee_tier,
            int(amount_in),  
            0  
        ).call()
        return amount_out
    except Exception as e:
        execution_logger.error(f"Error fetching quote for {token_in} -> {token_out} with amount {amount_in}: {e}")
        return None


def calculate_execution_price(amount_in, token_in, token_out, pair_contract):
    token0_address = pair_contract.functions.token0().call()
    token1_address = pair_contract.functions.token1().call()

    reserve0, reserve1 = get_reserves(pair_contract, token0_address, token1_address)
    if reserve0 is None or reserve1 is None:
        execution_logger.error("Reserves not fetched correctly. Aborting execution price calculation.")
        return None

    decimals_in = get_token_decimals(token_in)
    decimals_out = get_token_decimals(token_out)
    amount_in_human = Decimal(amount_in) / Decimal(10 ** decimals_in)

    # Convert reserves to Decimal
    reserve0 = Decimal(str(reserve0))
    reserve1 = Decimal(str(reserve1))

    if token_in == token0_address:
        amount_out = (amount_in_human * reserve1) / (reserve0 + amount_in_human)
    else:
        amount_out = (amount_in_human * reserve0) / (reserve1 + amount_in_human)

    amount_out = amount_out * Decimal(10 ** decimals_out)
    
    execution_logger.info(f"Execution Price: {amount_in_human} {token_in} -> {amount_out} {token_out}")
    return amount_out

def get_reserves(pair_contract, token0_address, token1_address):
    try:
        reserves = pair_contract.functions.getReserves().call()
        decimals0 = get_token_decimals(token0_address)
        decimals1 = get_token_decimals(token1_address)
        reserve0 = Decimal(reserves[0]) / Decimal(10 ** decimals0)
        reserve1 = Decimal(reserves[1]) / Decimal(10 ** decimals1)
        return reserve0, reserve1
    except Exception as e:
        execution_logger.error(f"Error fetching reserves: {e}")
        return None, None

def decode_balancer_error(error_data):
    if error_data.startswith('0x08c379a0'):
        error_message = bytes.fromhex(error_data[10:]).decode('utf-8')
        error_message = error_message.rstrip('\x00')
        return error_message
    return "Unknown error"
def push_to_redis(log_data):
    try:
        redis_client.lpush('arbitrage_paths', json.dumps(log_data))
        # Trim the list to keep the most recent 50 entries
        redis_client.ltrim('arbitrage_paths', 0, 49)
        main_logger.info("Arbitrage data pushed to Redis successfully: %s", log_data)  # Log the actual data being pushed
    except Exception as e:
        main_logger.error(f"Error pushing data to Redis: {str(e)}")

def run_data_detection_report(duration_minutes=60):
    start_time = time.time()
    end_time = start_time + (duration_minutes * 60)
    
    graph = load_configurations_from_redis()
    paths = generate_arbitrage_paths(graph)

    total_paths_checked = 0
    profitable_paths = 0
    total_profit = 0
    max_profit_percentage = 0
    profit_distribution = defaultdict(int)

    main_logger.info(f"Starting data detection performance report for {duration_minutes} minutes")

    while time.time() < end_time:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            process_path = partial(process_arbitrage_path, min_amount=1000, max_amount=10000, step_size=1000)
            results = list(executor.map(process_path, paths))
        
        for result in results:
            total_paths_checked += 1
            if result is not None:
                profitable_paths += 1
                total_profit += result['expected_profit']
                profit_percentage = (result['expected_profit'] / result['optimal_amount']) * 100
                max_profit_percentage = max(max_profit_percentage, profit_percentage)
                
                # Categorize profit percentages
                if profit_percentage < 1:
                    profit_distribution['0-1%'] += 1
                elif profit_percentage < 2:
                    profit_distribution['1-2%'] += 1
                elif profit_percentage < 5:
                    profit_distribution['2-5%'] += 1
                else:
                    profit_distribution['5%+'] += 1

        time.sleep(10)  # Wait for 10 seconds before the next round

    # Prepare the report
    report = {
        'duration_minutes': duration_minutes,
        'total_paths_checked': total_paths_checked,
        'profitable_paths': profitable_paths,
        'total_profit': float(total_profit),
        'average_profit': float(total_profit / profitable_paths) if profitable_paths > 0 else 0,
        'max_profit_percentage': float(max_profit_percentage),
        'profit_distribution': dict(profit_distribution)
    }

    # Save report to Redis
    redis_client.set('data_detection_report', json.dumps(report))
    main_logger.info("Performance report saved to Redis")

    return report
def log_path_details(path, optimal_amount):
    data_detection_logger.info(f"Path details for optimal amount {optimal_amount}:")
    amount = optimal_amount
    for i, (pool, token_in, token_out) in enumerate(path):
        if not pool.is_v3:
            pair_contract = w3.eth.contract(address=pool.address, abi=UNISWAP_V2_PAIR_ABI)
            amount_out = calculate_execution_price(amount, token_in.address, token_out.address, pair_contract)
            amount_out = amount_out * Decimal('0.997')  # Apply Uniswap V2 fee
        else:
            amount_out = get_quote(token_in.address, token_out.address, amount, pool.fee)
        
        data_detection_logger.info(f"  Swap {i+1}: {amount} {token_in.symbol} -> {amount_out} {token_out.symbol}")
        amount = amount_out
# Main function
def main():
    try:
        # Run the data detection report for 60 minutes
        report = run_data_detection_report(duration_minutes=60)
        
        # Log the report
        main_logger.info("Data Detection Performance Report:")
        main_logger.info(json.dumps(report, indent=2))
        
    except KeyboardInterrupt:
        main_logger.info("Script stopped by user.")
if __name__ == "__main__":
    main()
