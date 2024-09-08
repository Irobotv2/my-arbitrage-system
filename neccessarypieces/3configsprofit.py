import redis
import json
import logging
import time
from collections import defaultdict
from web3 import Web3
# Set up logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

# Define constants for the Ethereum node
INFURA_URL = 'http://localhost:8545'  # Replace with your Ethereum node URL
QUOTER_CONTRACT_ADDRESS = '0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6'  # Uniswap V3 Quoter contract address on Ethereum mainnet
UNISWAP_V2_ROUTER_ADDRESS = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
UNISWAP_V3_ROUTER_ADDRESS = "0xE592427A0AEce92De3Edee1F18E0157C05861564"

# Define your wallet address and private key
wallet_address = "0x6f2F4f0210AC805D817d4CD0b9A4D0c29d232E93"
private_key = "6575ac283b8aa1cbd913d2d28557e318048f8e62a5a19a74001988e2f40ab06c"  # Replace with your actual private key

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

# Uniswap V3 Quoter ABI
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

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Connect to the Ethereum node
w3 = Web3(Web3.HTTPProvider(INFURA_URL))

# Initialize Uniswap V3 Quoter contract
quoter_contract = w3.eth.contract(address=w3.to_checksum_address(QUOTER_CONTRACT_ADDRESS), abi=QUOTER_ABI)

# Full Uniswap V2 Pair ABI
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

# Define token decimals
TOKEN_DECIMALS = {
    '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48': 6,  # USDC
    '0x6b175474e89094c44da98b954eedeac495271d0f': 18, # DAI
    '0xc02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2': 18, # WETH
    '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599': 8,  # WBTC
    # Add more tokens and their decimals as needed
}

#DATADETECTIONALGORITHM
def get_token_decimals(token_address):
    return TOKEN_DECIMALS.get(token_address.lower(), 18)  # Default to 18 if not found

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
        self.tokens = {}  # address -> Token
        self.pools = []   # List of all pools
        self.edges = defaultdict(lambda: defaultdict(list))  # token_address -> token_address -> [Pool]

    def add_token(self, token):
        if token.address not in self.tokens:
            self.tokens[token.address] = token

    def add_pool(self, pool):
        self.pools.append(pool)
        self.edges[pool.token0.address][pool.token1.address].append(pool)
        self.edges[pool.token1.address][pool.token0.address].append(pool)


def load_configurations_from_redis():
    logging.info("Loading configurations from Redis...")
    graph = PoolGraph()
    
    # List all the configuration keys in Redis to be loaded
    configuration_keys = ['USDC_WETH_config', 'WETH_DAI_config', 'DAI_WBTC_config']

    for config_key in configuration_keys:
        config_json = redis_client.get(config_key)
        if config_json:
            config = json.loads(config_json)
            token0 = Token(config['token0']['address'], config['token0']['symbol'])
            token1 = Token(config['token1']['address'], config['token1']['symbol'])
            graph.add_token(token0)
            graph.add_token(token1)

            # Add Uniswap V2 pool
            if config.get('v2_pool'):
                pool = Pool(config['v2_pool'], token0, token1, 3000, False)
                graph.add_pool(pool)

            # Add Uniswap V3 pools
            for fee_tier, v3_pool_info in config.get('v3_pools', {}).items():
                pool = Pool(v3_pool_info['address'], token0, token1, int(float(fee_tier[:-1]) * 10000), True)
                graph.add_pool(pool)

    logging.info(f"Loaded {len(graph.tokens)} tokens and {len(graph.pools)} pools from configurations")
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

    logging.info(f"Generated {len(paths)} potential arbitrage paths")
    return paths

def format_path(path):
    result = ["Path:"]
    for i, (pool, token_in, token_out) in enumerate(path, 1):
        pool_type = "V2" if not pool.is_v3 else f"V3/{pool.fee/10000:.2f}%"
        result.append(f"{i}: {token_in.symbol} -> {token_out.symbol} ({pool_type})")
    return "\n".join(result)

def calculate_execution_price(amount_in, token_in, token_out, pair_contract):
    token0_address = pair_contract.functions.token0().call()
    token1_address = pair_contract.functions.token1().call()

    reserve0, reserve1 = get_reserves(pair_contract, token0_address, token1_address)
    if reserve0 is None or reserve1 is None:
        logging.error("Reserves not fetched correctly. Aborting execution price calculation.")
        return None

    decimals_in = get_token_decimals(token_in)
    decimals_out = get_token_decimals(token_out)
    amount_in_human = amount_in / (10 ** decimals_in)

    if token_in == token0_address:
        amount_out = (amount_in_human * reserve1) / (reserve0 + amount_in_human)
    else:
        amount_out = (amount_in_human * reserve0) / (reserve1 + amount_in_human)

    amount_out = amount_out * (10 ** decimals_out)
    
    logging.info(f"Execution Price: {amount_in_human} {token_in} -> {amount_out} {token_out}")
    return amount_out

def get_reserves(pair_contract, token0_address, token1_address):
    try:
        reserves = pair_contract.functions.getReserves().call()
        decimals0 = get_token_decimals(token0_address)
        decimals1 = get_token_decimals(token1_address)
        reserve0 = reserves[0] / (10 ** decimals0)
        reserve1 = reserves[1] / (10 ** decimals1)
        return reserve0, reserve1
    except Exception as e:
        logging.error(f"Error fetching reserves: {e}")
        return None, None

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
        logging.error(f"Error fetching quote for {token_in} -> {token_out} with amount {amount_in}: {e}")
        return None

def log_arbitrage_opportunity(path, input_amount, output_amount):
    with open("arbitrage_opportunities.log", "a") as log_file:
        log_file.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_file.write(format_path(path) + "\n")
        log_file.write(f"Input Amount: {input_amount:.6f} {path[0][1].symbol}\n")
        log_file.write(f"Output Amount: {output_amount:.6f} {path[0][1].symbol}\n")
        log_file.write(f"Profit: {output_amount - input_amount:.6f} {path[0][1].symbol}\n")
        log_file.write(f"Profit %: {((output_amount - input_amount) / input_amount) * 100:.2f}%\n")
        log_file.write("-" * 50 + "\n")

def log_path_to_redis(path, input_amount, output_amount, profit, profit_percentage):
    log_data = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'path': format_path(path),
        'input_amount': input_amount,
        'output_amount': output_amount,
        'profit': profit,
        'profit_percentage': profit_percentage
    }
    # Push the log to a Redis list
    redis_client.lpush('arbitrage_paths', json.dumps(log_data))

def simulate_arbitrage_for_path(path, starting_amount):
    """
    Simulates an arbitrage path for a given starting amount.
    """
    starting_token = path[0][1]
    decimals_starting_token = get_token_decimals(starting_token.address)
    starting_amount_in = starting_amount * (10 ** decimals_starting_token)

    logging.info(format_path(path))

    pool1, token_in, token_out = path[0]
    if not pool1.is_v3:
        pair_contract = w3.eth.contract(address=pool1.address, abi=UNISWAP_V2_PAIR_ABI)
        amount_out = calculate_execution_price(starting_amount_in, token_in.address, token_out.address, pair_contract)
    else:
        amount_out = get_quote(token_in.address, token_out.address, starting_amount_in, pool1.fee)

    if amount_out is None:
        logging.error("Failed to get amount out for first swap. Aborting path simulation.")
        return None, None

    pool2, token_in, token_out = path[1]
    if pool2.is_v3:
        final_amount = get_quote(token_in.address, token_out.address, amount_out, pool2.fee)
    else:
        pair_contract = w3.eth.contract(address=pool2.address, abi=UNISWAP_V2_PAIR_ABI)
        final_amount = calculate_execution_price(amount_out, token_in.address, token_out.address, pair_contract)

    if final_amount is None:
        logging.error("Failed to get final amount for second swap. Aborting path simulation.")
        return None, None

    final_amount_hr = final_amount / (10 ** decimals_starting_token)
    profit = final_amount_hr - starting_amount
    profit_percentage = (profit / starting_amount) * 100 if starting_amount != 0 else 0

    logging.info(f"Final Token Amount: {final_amount_hr:.6f} {starting_token.symbol}")
    logging.info(f"Profit: {profit:.6f} {starting_token.symbol}")
    logging.info(f"Profit %: {profit_percentage:.2f}%")
    logging.info("-" * 50)

    return profit, profit_percentage


def find_optimal_amount_for_arbitrage(path, min_amount, max_amount, step_size):
    """
    Finds the optimal input amount for an arbitrage path by simulating different amounts.
    """
    optimal_amount = min_amount
    max_profit = float('-inf')

    for amount in range(min_amount, max_amount + 1, step_size):
        logging.info(f"Simulating with input amount: {amount}")
        profit, profit_percentage = simulate_arbitrage_for_path(path, amount)

        if profit is not None and profit > max_profit:
            max_profit = profit
            optimal_amount = amount

    logging.info(f"Optimal amount: {optimal_amount} with maximum profit: {max_profit:.6f}")
    return optimal_amount, max_profit






#LIQUIDITYVAULTSTOFUNDTHEPATHS
FLASHLOAN_BUNDLE_EXECUTOR_ABI = [
    {
        "inputs": [
            {
                "internalType": "address",
                "name": "_executor",
                "type": "address"
            }
        ],
        "stateMutability": "nonpayable",
        "type": "constructor"
    },
    {
        "inputs": [],
        "name": "executor",
        "outputs": [
            {
                "internalType": "address",
                "name": "",
                "type": "address"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {
                "internalType": "contract IERC20[]",
                "name": "tokens",
                "type": "address[]"
            },
            {
                "internalType": "uint256[]",
                "name": "amounts",
                "type": "uint256[]"
            },
            {
                "internalType": "address[]",
                "name": "targets",
                "type": "address[]"
            },
            {
                "internalType": "bytes[]",
                "name": "payloads",
                "type": "bytes[]"
            }
        ],
        "name": "initiateFlashLoanAndBundle",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "owner",
        "outputs": [
            {
                "internalType": "address",
                "name": "",
                "type": "address"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {
                "internalType": "contract IERC20[]",
                "name": "tokens",
                "type": "address[]"
            },
            {
                "internalType": "uint256[]",
                "name": "amounts",
                "type": "uint256[]"
            },
            {
                "internalType": "uint256[]",
                "name": "feeAmounts",
                "type": "uint256[]"
            },
            {
                "internalType": "bytes",
                "name": "userData",
                "type": "bytes"
            }
        ],
        "name": "receiveFlashLoan",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]
# Contract instance
# Contract instance
flashloan_executor = w3.eth.contract(address=contract_address, abi=FLASHLOAN_BUNDLE_EXECUTOR_ABI)

# Chainlink price feed addresses (including USDC)
price_feeds = {
    'WETH': Web3.to_checksum_address('0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419'),
    'wstETH': Web3.to_checksum_address('0xb4b0343a7a3b9f59b2c1e3a75e5e37d104f46f67'),
    'AAVE': Web3.to_checksum_address('0x547a514d5e3769680Ce22B2361c10Ea13619e8a9'),
    'BAL': Web3.to_checksum_address('0xdf2917806e30300537aeb49a7663062f4d1f2b5f'),
    'rETH': Web3.to_checksum_address('0x536218f9E9Eb48863970252233c8F271f554C2d0'),
    'USDC': Web3.to_checksum_address('0x8fFfFfd4AfB6115b954Bd326cbe7B4BA576818f6'),  # Chainlink USDC/USD price feed
}

# Update the tokens_and_pools dictionary to use checksum addresses (including USDC)
tokens_and_pools = {
    'WETH': {'address': Web3.to_checksum_address('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'), 'pool': Web3.to_checksum_address('0xDACf5Fa19b1f720111609043ac67A9818262850c')},
    'wstETH': {'address': Web3.to_checksum_address('0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0'), 'pool': Web3.to_checksum_address('0x3de27EFa2F1AA663Ae5D458857e731c129069F29')},
    'AAVE': {'address': Web3.to_checksum_address('0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9'), 'pool': Web3.to_checksum_address('0x3de27EFa2F1AA663Ae5D458857e731c129069F29')},
    'BAL': {'address': Web3.to_checksum_address('0xba100000625a3754423978a60c9317c58a424e3D'), 'pool': Web3.to_checksum_address('0x5c6Ee304399DBdB9C8Ef030aB642B10820DB8F56')},
    'rETH': {'address': Web3.to_checksum_address('0xae78736Cd615f374D3085123A210448E74Fc6393'), 'pool': Web3.to_checksum_address('0x1E19CF2D73a72Ef1332C882F20534B6519Be0276')},
    'sDAI': {'address': Web3.to_checksum_address('0x83F20F44975D03b1b09e64809B757c47f942BEeA'), 'pool': Web3.to_checksum_address('0x2191Df821C198600499aA1f0031b1a7514D7A7D9')},
    'osETH': {'address': Web3.to_checksum_address('0xf1C9acDc66974dFB6dEcB12aA385b9cD01190E38'), 'pool': Web3.to_checksum_address('0xDACf5Fa19b1f720111609043ac67A9818262850c')},
    'GYD': {'address': Web3.to_checksum_address('0x1FaE95096322828B3Ef2a8617E1026D80549d8cb'), 'pool': Web3.to_checksum_address('0x2191Df821C198600499aA1f0031b1a7514D7A7D9')},
    'USDC': {'address': Web3.to_checksum_address('0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606EB48'), 'pool': Web3.to_checksum_address('0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606EB48')},  # Example pool address for USDC
}

# ABI for Chainlink price feed
price_feed_abi = [
    {
        "inputs": [],
        "name": "latestAnswer",
        "outputs": [{"internalType": "int256", "name": "", "type": "int256"}],
        "stateMutability": "view",
        "type": "function"
    }
]

def get_token_price(token, max_retries=3, delay=1):
    if token in price_feeds:
        price_feed_contract = w3.eth.contract(address=price_feeds[token], abi=price_feed_abi)
        for attempt in range(max_retries):
            try:
                price = price_feed_contract.functions.latestAnswer().call()
                return price
            except (ContractLogicError, BadFunctionCallOutput) as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to get price for {token} after {max_retries} attempts. Error: {str(e)}")
                    if token == 'wstETH':
                        logger.info(f"Using fallback price for wstETH")
                        return 2500 * 10**8  # Assuming 1 wstETH ≈ 2500 USD
                    return None
                time.sleep(delay)
    return None

def select_token_for_flashloan(config):
    selected_token = config.get("token1", {}).get("symbol")
    logger.info(f"Selected token for flash loan: {selected_token}")
    
    if selected_token in tokens_and_pools:
        pool_address = tokens_and_pools[selected_token]['pool']
        logger.info(f"Selected pool for flash loan: {pool_address} for token {selected_token}")
        return selected_token, pool_address
    else:
        logger.error(f"No pool found for the selected token: {selected_token}")
        return None, None
# Helper functions
def decode_balancer_error(error_data):
    if error_data.startswith('0x08c379a0'):
        # Remove the selector and convert to text
        error_message = bytes.fromhex(error_data[10:]).decode('utf-8')
        # Remove padding zeros
        error_message = error_message.rstrip('\x00')
        return error_message
    return "Unknown error"
def prepare_approval_payloads(sorted_tokens, flash_loan_amount):
    return [
        w3_exec.eth.contract(address=token, abi=ERC20_ABI).encodeABI(
            fn_name="approve",
            args=[FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS, flash_loan_amount]
        ) for token in sorted_tokens
    ]






#EXECUTETHEWHOLETHING
def execute_arbitrage(opportunity):
    """
    Execute an arbitrage opportunity by crafting and submitting transactions as bundles to builders.
    """
    token0_address = opportunity['token0']['address']
    token1_address = opportunity['token1']['address']
    v3_pool_info = opportunity['v3_pool']
    is_v2_to_v3 = opportunity['direction'] == 'v2_to_v3'
    price_difference = opportunity['price_difference']

    sorted_tokens = sort_tokens(token0_address, token1_address)

    # Check liquidity for V3 pool
    v3_pool_contract = w3_local.eth.contract(address=v3_pool_info['address'], abi=V3_POOL_ABI)
    liquidity = v3_pool_contract.functions.liquidity().call()
    
    if Decimal(liquidity) / Decimal(10 ** 18) < MIN_LIQUIDITY_THRESHOLD_ETH:
        main_logger.warning(f"V3 pool {v3_pool_info['address']} has insufficient liquidity. Skipping arbitrage execution.")
        return

    # Calculate optimal flash loan amount
    optimal_amount_eth = calculate_optimal_flashloan_amount(v3_pool_info['address'], price_difference)
    flash_loan_amount = w3_exec.to_wei(optimal_amount_eth, 'ether')

    main_logger.info(f"Executing arbitrage with flash loan amount: {flash_loan_amount} wei")
    main_logger.info(f"Token0: {token0_address}, Token1: {token1_address}")
    main_logger.info(f"Sorted tokens: {sorted_tokens}")

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
        nonce = w3_exec.eth.get_transaction_count(wallet_address)
        gas_price = w3_exec.eth.gas_price

        # Estimate gas
        gas_limit = estimate_gas(tokens, amounts, all_targets, all_payloads, nonce)

        tx = build_transaction(tokens, amounts, all_targets, all_payloads, nonce, gas_limit, gas_price)
        
        signed_tx = w3_exec.eth.account.sign_transaction(tx, private_key=private_key)
        tx_hash = w3_exec.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        # Log submitted transaction
        log_submitted_transaction(tx_hash, opportunity, flash_loan_amount)

        # Prepare and send the transaction bundle
        send_bundle(signed_tx, opportunity)

        # Wait for transaction receipt and log the result
        receipt = w3_exec.eth.wait_for_transaction_receipt(tx_hash)
        log_transaction_result(receipt, tx_hash, opportunity, flash_loan_amount)

    except Exception as e:
        handle_transaction_error(e)
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
        main_logger.warning(f"Gas estimation failed: {str(gas_error)}. Using default gas limit.")
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
    submitted_logger.info(f"Arbitrage transaction submitted - Hash: {tx_hash.hex()}, Pair: {opportunity['name']}, Type: {'V2 to V3' if opportunity['direction'] == 'v2_to_v3' else 'V3 to V2'}, Amount: {flash_loan_amount}, Fee Tier: {opportunity['v3_pool']['fee']}")


def send_bundle(signed_tx, opportunity):
    transaction_bundle = {
        "txs": [signed_tx.rawTransaction.hex()],
        "blockNumber": w3_exec.eth.block_number + 1,
        "minTimestamp": int(time.time()),
        "maxTimestamp": int(time.time()) + 60,  # Bundle valid for the next 60 seconds
        "revertingTxHashes": []
    }
    main_logger.info(f"Transaction bundle details: {json.dumps(transaction_bundle, indent=2)}")
    send_bundle_to_builders(transaction_bundle)

def log_transaction_result(receipt, tx_hash, opportunity, flash_loan_amount):
    if receipt['status'] == 1:
        confirmed_logger.info(f"Arbitrage transaction confirmed - Hash: {tx_hash.hex()}, Pair: {opportunity['name']}, Type: {'V2 to V3' if opportunity['direction'] == 'v2_to_v3' else 'V3 to V2'}, Amount: {flash_loan_amount}, Fee Tier: {opportunity['v3_pool']['fee']}, Gas Used: {receipt['gasUsed']}, Effective Gas Price: {receipt['effectiveGasPrice']}")
        main_logger.info(f"Flashloan transaction mined successfully. Hash: {tx_hash.hex()}")
    else:
        main_logger.error(f"Flashloan transaction failed. Hash: {tx_hash.hex()}")

def handle_transaction_error(error):
    error_message = str(error)
    if "execution reverted" in error_message:
        error_data = error_message.split("execution reverted:")[-1].strip()
        decoded_error = decode_balancer_error(error_data)
        if "BAL#" in decoded_error:
            main_logger.error(f"Balancer error detected: {decoded_error}")
            if "BAL#528" in decoded_error:
                main_logger.error("Encountered BAL#528 error. This might indicate an issue with the flash loan or token approvals.")
        else:
            main_logger.error(f"Execution reverted: {decoded_error}")
    elif "SafeMath: subtraction overflow" in error_message:
        main_logger.error(f"Insufficient token balance: {error_message}")
    elif "UniswapV2Library: INSUFFICIENT_INPUT_AMOUNT" in error_message:
        main_logger.error(f"Insufficient input amount: {error_message}")
    else:
        main_logger.error(f"Error executing flashloan arbitrage: {error_message}", exc_info=True)

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
            main_logger.info(f"Sending bundle to {url} with payload: {json.dumps(bundle, indent=2)}")
            response = requests.post(url, json=bundle, headers=headers)

            if response.status_code == 200:
                main_logger.info(f"Bundle sent successfully to {url}: {response.json()}")
            else:
                main_logger.warning(f"Failed to send bundle to {url}: {response.status_code} - {response.text}")
        except Exception as e:
            main_logger.error(f"Error sending bundle to {url}: {str(e)}")
def main():
    graph = load_configurations_from_redis()
    paths = generate_arbitrage_paths(graph)

    logging.info(f"Generated {len(paths)} potential arbitrage paths")

    try:
        while True:
            for i, path in enumerate(paths, 1):
                # Check initial profitability with base amount
                base_amount = 1000
                profit, profit_percentage = simulate_arbitrage_for_path(path, base_amount)

                if profit is not None and profit > 0:
                    logging.info(f"Profitable path found with base amount {base_amount}. Finding optimal input amount...")
                    optimal_amount, max_profit = find_optimal_amount_for_arbitrage(path, min_amount=100, max_amount=5000, step_size=100)

                    # Log the optimal amount and potential profit
                    log_path_to_redis(path, optimal_amount, optimal_amount + max_profit, max_profit, (max_profit / optimal_amount) * 100)

                    # If a profitable opportunity is found, execute the arbitrage
                    opportunity = {
                        'token0': {'address': path[0][1].address},
                        'token1': {'address': path[1][1].address},
                        'v3_pool': {'address': path[1][0].address, 'fee': path[1][0].fee},
                        'direction': 'v2_to_v3' if path[0][0].is_v3 == False and path[1][0].is_v3 == True else 'v3_to_v2',
                        'price_difference': profit_percentage,
                        'name': f"{path[0][1].symbol}/{path[1][1].symbol}"
                    }

                    logging.info(f"Executing arbitrage opportunity for path: {format_path(path)}")
                    execute_arbitrage(opportunity)

            time.sleep(60)  # Wait for 60 seconds before the next round
    except KeyboardInterrupt:
        logging.info("Script stopped by user.")

if __name__ == "__main__":
    main()
