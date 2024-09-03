#ALLCONFIGS.PY
import redis
from web3 import Web3
import json
import time
import logging
from datetime import datetime
from web3.middleware import geth_poa_middleware
from eth_account import Account
from logging.handlers import RotatingFileHandler
import os
from decimal import Decimal

# Initialize logging
logging.basicConfig(level=logging.INFO)

# Setup Web3 connection for querying data (localhost)
provider_url_localhost = 'http://localhost:8545'
w3_local = Web3(Web3.HTTPProvider(provider_url_localhost, request_kwargs={'timeout': 30}))

# Setup Web3 connection for executing transactions (Tenderly RPC)
provider_url_exec = 'https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c'
w3_exec = Web3(Web3.HTTPProvider(provider_url_exec))
w3_exec.middleware_onion.inject(geth_poa_middleware, layer=0)

# Define your wallet address and private key
wallet_address = "0x19F5034FAB7e2CcA2Ad46EC28acF20cbd098D3fF"
private_key = "6d0ad7f50dccb88715e3592f39ea5be4c715531223b2daeb2de621dc8f6c230f"  # Replace with your actual private key

# Define contract addresses
UNISWAP_V2_ROUTER_ADDRESS = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
UNISWAP_V3_ROUTER_ADDRESS = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS = "0x26B7B5AB244114ab88578D5C4cD5b096097bf543"

# ABIs
V2_POOL_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"internalType": "uint112", "name": "_reserve0", "type": "uint112"},
            {"internalType": "uint112", "name": "_reserve1", "type": "uint112"},
            {"internalType": "uint32", "name": "_blockTimestampLast", "type": "uint32"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

V2_ROUTER_ABI = [
    {
        "name": "swapExactTokensForTokens",
        "type": "function",
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "amountOutMin", "type": "uint256"},
            {"name": "path", "type": "address[]"},
            {"name": "to", "type": "address"},
            {"name": "deadline", "type": "uint256"}
        ],
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "stateMutability": "nonpayable",
        "type": "function"
    }
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

V3_ROUTER_ABI = [
    {
        "name": "exactInputSingle",
        "type": "function",
        "inputs": [
            {
                "name": "params",
                "type": "tuple",
                "components": [
                    {"name": "tokenIn", "type": "address"},
                    {"name": "tokenOut", "type": "address"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "recipient", "type": "address"},
                    {"name": "deadline", "type": "uint256"},
                    {"name": "amountIn", "type": "uint256"},
                    {"name": "amountOutMinimum", "type": "uint256"},
                    {"name": "sqrtPriceLimitX96", "type": "uint160"}
                ]
            }
        ],
        "outputs": [{"name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
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

# Create contract instances
v2_router_contract = w3_exec.eth.contract(address=UNISWAP_V2_ROUTER_ADDRESS, abi=V2_ROUTER_ABI)
v3_router_contract = w3_exec.eth.contract(address=UNISWAP_V3_ROUTER_ADDRESS, abi=V3_ROUTER_ABI)
flashloan_contract = w3_exec.eth.contract(address=FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS, abi=FLASHLOAN_BUNDLE_EXECUTOR_ABI)

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Global variables
REPORT_INTERVAL = 2 * 60 * 60  # 2 hours in seconds
DETECTION_THRESHOLD = 0.005  # 0.5% threshold for detecting opportunities
EXECUTION_THRESHOLD = 0.01   # 1% threshold for executing arbitrage
opportunities = []

def load_configurations_from_redis():
    configs = {}
    for key in redis_client.keys('*_config'):
        config_json = redis_client.get(key)
        config = json.loads(config_json)
        configs[key.decode('utf-8')] = config
    return configs

def get_token_decimals(token_address):
    token_contract = w3_local.eth.contract(address=token_address, abi=ERC20_ABI)
    return token_contract.functions.decimals().call()

def sqrt_price_x96_to_price(sqrt_price_x96, token0_decimals, token1_decimals):
    try:
        sqrt_price = Decimal(sqrt_price_x96) / Decimal(2 ** 96)
        price = sqrt_price ** 2
        decimal_adjustment = Decimal(10 ** (token1_decimals - token0_decimals))
        adjusted_price = price * decimal_adjustment
        
        logging.info(f"V3 Price Calculation: sqrt_price_x96={sqrt_price_x96}, "
                     f"sqrt_price={sqrt_price}, price={price}, "
                     f"decimal_adjustment={decimal_adjustment}, adjusted_price={adjusted_price}")
        
        if adjusted_price <= 0:
            logging.warning(f"V3 Price is zero or negative: {adjusted_price}")
        
        return float(adjusted_price)
    except Exception as e:
        logging.error(f"Error calculating V3 price: {str(e)}")
        return None
def get_price_v2(pool_contract, token0_decimals, token1_decimals):
    try:
        reserves = pool_contract.functions.getReserves().call()
        reserve0 = Decimal(reserves[0])
        reserve1 = Decimal(reserves[1])
        
        normalized_reserve0 = reserve0 / Decimal(10 ** token0_decimals)
        normalized_reserve1 = reserve1 / Decimal(10 ** token1_decimals)

        price = normalized_reserve1 / normalized_reserve0
        
        logging.info(f"V2 Price Calculation: reserve0={reserve0}, reserve1={reserve1}, "
                     f"normalized_reserve0={normalized_reserve0}, normalized_reserve1={normalized_reserve1}, "
                     f"price={price}")
        
        if price <= 0:
            logging.warning(f"V2 Price is zero or negative: {price}")
        
        return float(price)
    except Exception as e:
        logging.error(f"Error calculating V2 price: {str(e)}")
        return None

def get_price_v3(pool_contract, token0_decimals, token1_decimals):
    try:
        slot0_data = pool_contract.functions.slot0().call()
        sqrt_price_x96 = slot0_data[0]
        return sqrt_price_x96_to_price(sqrt_price_x96, token0_decimals, token1_decimals)
    except Exception as e:
        logging.error(f"Error getting V3 slot0 data: {str(e)}")
        return None

def sort_tokens(token_a, token_b):
    return (token_a, token_b) if token_a.lower() < token_b.lower() else (token_b, token_a)

def calculate_optimal_flashloan_amount(v3_pool_address, price_difference):
    try:
        v3_pool_contract = w3_local.eth.contract(address=v3_pool_address, abi=V3_POOL_ABI)
        liquidity = v3_pool_contract.functions.liquidity().call()
        
        # Convert liquidity to ether equivalent
        max_amount = w3_exec.from_wei(liquidity, 'ether')
        
        # Calculate optimal amount based on price difference
        # Ensure it's between 1 and 100 WETH
        optimal_amount = max(min(max_amount * (price_difference / 100), 100), 1)
        
        main_logger.info(f"Liquidity: {liquidity}, Max amount: {max_amount}, Price difference: {price_difference}, Optimal amount: {optimal_amount}")
        
        return optimal_amount
    except Exception as e:
        main_logger.error(f"Error calculating optimal flashloan amount: {str(e)}")
        return 1  # Return 1 WETH as a fallback

# Add this function near the top of your script, after the imports
def setup_logger(name, log_file, level=logging.INFO):
    formatter = logging.Formatter('%(asctime)s - %(message)s')
    handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger

# Create loggers (add this after the setup_logger function)
main_logger = setup_logger('main_logger', 'arbitrage_bot.log')
submitted_logger = setup_logger('submitted_transactions', 'submitted_transactions.log')
confirmed_logger = setup_logger('confirmed_transactions', 'confirmed_transactions.log')

def approve_tokens(token_address, amount):
    token_contract = w3_exec.eth.contract(address=token_address, abi=ERC20_ABI)
    nonce = w3_exec.eth.get_transaction_count(wallet_address)
    
    tx = token_contract.functions.approve(
        FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS,
        amount
    ).build_transaction({
        'from': wallet_address,
        'nonce': nonce,
        'gas': 100000,
        'gasPrice': w3_exec.eth.gas_price,
    })
    
    signed_tx = w3_exec.eth.account.sign_transaction(tx, private_key=private_key)
    tx_hash = w3_exec.eth.send_raw_transaction(signed_tx.rawTransaction)
    w3_exec.eth.wait_for_transaction_receipt(tx_hash)


def decode_balancer_error(error_data):
    if error_data.startswith('0x08c379a0'):
        # Remove the selector and convert to text
        error_message = bytes.fromhex(error_data[10:]).decode('utf-8')
        # Remove padding zeros
        error_message = error_message.rstrip('\x00')
        return error_message
    return "Unknown error"
def execute_arbitrage(config, v3_pool_info, is_v2_to_v3, price_difference):
    token0_address = config['token0']['address']
    token1_address = config['token1']['address']
    
    sorted_tokens = sort_tokens(token0_address, token1_address)

    # Check liquidity
    v3_pool_contract = w3_local.eth.contract(address=v3_pool_info['address'], abi=V3_POOL_ABI)
    liquidity = v3_pool_contract.functions.liquidity().call()
    
    if liquidity == 0:
        main_logger.warning(f"Zero liquidity in pool {v3_pool_info['address']}. Skipping arbitrage execution.")
        return

    # Calculate optimal flash loan amount between 1 and 100 WETH
    optimal_amount_eth = max(min(price_difference, 100), 1)
    flash_loan_amount = w3_exec.to_wei(optimal_amount_eth, 'ether')
    
    main_logger.info(f"Calculated optimal flash loan amount: {optimal_amount_eth} WETH ({flash_loan_amount} wei)")

    # Rest of the function remains the same...
    main_logger.info(f"Executing arbitrage with flash loan amount: {flash_loan_amount} wei")
    main_logger.info(f"Token0: {token0_address}, Token1: {token1_address}")
    main_logger.info(f"Sorted tokens: {sorted_tokens}")

    slippage = 0.005  # 0.5% slippage
    min_amount_out = int(flash_loan_amount * (1 - slippage))
    deadline = int(time.time()) + 60 * 2  # 2-minute deadline

    main_logger.info(f"Slippage: {slippage}, Min amount out: {min_amount_out}, Deadline: {deadline}")

    # Prepare approval payloads
    approval_payloads = []
    for token in sorted_tokens:
        approval_payload = w3_exec.eth.contract(address=token, abi=ERC20_ABI).encodeABI(
            fn_name="approve",
            args=[FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS, flash_loan_amount]
        )
        approval_payloads.append(approval_payload)

    # Prepare swap payloads
    if is_v2_to_v3:
        main_logger.info("Preparing V2 to V3 swap")
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
        swap_payloads = [v2_swap_payload, v3_swap_payload]
        swap_targets = [UNISWAP_V2_ROUTER_ADDRESS, UNISWAP_V3_ROUTER_ADDRESS]
    else:
        main_logger.info("Preparing V3 to V2 swap")
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
        swap_payloads = [v3_swap_payload, v2_swap_payload]
        swap_targets = [UNISWAP_V3_ROUTER_ADDRESS, UNISWAP_V2_ROUTER_ADDRESS]

    # Combine all payloads and targets
    all_payloads = approval_payloads + swap_payloads
    all_targets = sorted_tokens + swap_targets

    tokens = list(sorted_tokens)
    amounts = [flash_loan_amount, flash_loan_amount]

    main_logger.info(f"Tokens for flash loan: {tokens}")
    main_logger.info(f"Amounts for flash loan: {amounts}")
    main_logger.info(f"Targets: {all_targets}")
    main_logger.debug(f"Payloads: {all_payloads}")

    try:
        nonce = w3_exec.eth.get_transaction_count(wallet_address)
        gas_price = w3_exec.eth.gas_price

        main_logger.info(f"Nonce: {nonce}, Gas Price: {gas_price}")

        # Estimate gas
        try:
            gas_estimate = flashloan_contract.functions.initiateFlashLoanAndBundle(
                tokens, amounts, all_targets, all_payloads
            ).estimate_gas({'from': wallet_address, 'nonce': nonce})
            gas_limit = int(gas_estimate * 1.2)  # Add 20% buffer
            main_logger.info(f"Estimated gas: {gas_estimate}, Gas limit: {gas_limit}")
        except Exception as gas_error:
            main_logger.warning(f"Gas estimation failed: {str(gas_error)}. Using default gas limit.")
            gas_limit = 1000000  # Use a higher default gas limit due to complex transaction

        tx = flashloan_contract.functions.initiateFlashLoanAndBundle(
            tokens, amounts, all_targets, all_payloads
        ).build_transaction({
            'from': wallet_address,
            'nonce': nonce,
            'gas': gas_limit,
            'gasPrice': gas_price,
        })

        main_logger.info(f"Transaction built: {tx}")

        signed_tx = w3_exec.eth.account.sign_transaction(tx, private_key=private_key)
        tx_hash = w3_exec.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        # Log submitted transaction
        submitted_logger.info(f"Arbitrage transaction submitted - Hash: {tx_hash.hex()}, Pair: {config['name']}, Type: {'V2 to V3' if is_v2_to_v3 else 'V3 to V2'}, Amount: {flash_loan_amount}, Fee Tier: {v3_pool_info['fee']}")

        main_logger.info(f"Flashloan transaction sent. Hash: {tx_hash.hex()}")

        receipt = w3_exec.eth.wait_for_transaction_receipt(tx_hash)
        if receipt['status'] == 1:
            confirmed_logger.info(f"Arbitrage transaction confirmed - Hash: {tx_hash.hex()}, Pair: {config['name']}, Type: {'V2 to V3' if is_v2_to_v3 else 'V3 to V2'}, Amount: {flash_loan_amount}, Fee Tier: {v3_pool_info['fee']}, Gas Used: {receipt['gasUsed']}, Effective Gas Price: {receipt['effectiveGasPrice']}")
            main_logger.info(f"Flashloan transaction mined successfully. Hash: {tx_hash.hex()}")
        else:
            main_logger.error(f"Flashloan transaction failed. Hash: {tx_hash.hex()}")

        main_logger.info(f"Flashloan transaction details: Gas used: {receipt['gasUsed']}, Effective gas price: {receipt['effectiveGasPrice']}")

    except ValueError as ve:
        error_message = str(ve)
        if "execution reverted" in error_message:
            # Extract the error data
            error_data = error_message.split("execution reverted:")[-1].strip()
            decoded_error = decode_balancer_error(error_data)
            if "BAL#" in decoded_error:
                main_logger.error(f"Balancer error detected: {decoded_error}")
                # Here you can add specific handling for different Balancer error codes
                if "BAL#528" in decoded_error:
                    main_logger.error("Encountered BAL#528 error. This might indicate an issue with the flash loan or token approvals.")
                    # Add specific handling for BAL#528 error if needed
            else:
                main_logger.error(f"Execution reverted: {decoded_error}")
        elif "SafeMath: subtraction overflow" in error_message:
            main_logger.error(f"Insufficient token balance: {error_message}")
        elif "UniswapV2Library: INSUFFICIENT_INPUT_AMOUNT" in error_message:
            main_logger.error(f"Insufficient input amount: {error_message}")
        else:
            main_logger.error(f"ValueError in execute_arbitrage: {error_message}")
    except Exception as e:
        main_logger.error(f"Error executing flashloan arbitrage: {str(e)}", exc_info=True)

def approve_tokens(token_address, amount):
    token_contract = w3_exec.eth.contract(address=token_address, abi=ERC20_ABI)
    nonce = w3_exec.eth.get_transaction_count(wallet_address)
    
    tx = token_contract.functions.approve(
        FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS,
        amount
    ).build_transaction({
        'from': wallet_address,
        'nonce': nonce,
        'gas': 100000,
        'gasPrice': w3_exec.eth.gas_price,
    })
    
    signed_tx = w3_exec.eth.account.sign_transaction(tx, private_key=private_key)
    tx_hash = w3_exec.eth.send_raw_transaction(signed_tx.rawTransaction)
    w3_exec.eth.wait_for_transaction_receipt(tx_hash)
    main_logger.info(f"Approval transaction sent for token {token_address}. Hash: {tx_hash.hex()}")

def calculate_percentage_difference(v1, v2):
    """
    Calculate the percentage difference between two values.
    """
    v1, v2 = Decimal(str(v1)), Decimal(str(v2))
    return abs(v1 - v2) / ((v1 + v2) / Decimal('2')) * Decimal('100')

def calculate_profit_percentage(price_v2, price_v3, gas_cost, flash_loan_fee):
    """
    Calculate the profit percentage accounting for gas costs and flash loan fees.
    """
    # Convert to Decimal for precision
    price_v2 = Decimal(str(price_v2))
    price_v3 = Decimal(str(price_v3))
    gas_cost = Decimal(str(gas_cost))
    flash_loan_fee = Decimal(str(flash_loan_fee))

    # Determine the direction of arbitrage
    if price_v3 < price_v2:  # V3 to V2 arbitrage
        buy_price = price_v3
        sell_price = price_v2
    else:  # V2 to V3 arbitrage
        buy_price = price_v2
        sell_price = price_v3

    # Calculate the raw profit percentage
    raw_profit_percentage = (sell_price - buy_price) / buy_price * Decimal('100')

    # Estimate the transaction value (conservative estimate)
    transaction_value = buy_price

    # Convert gas cost to the same unit as prices
    gas_cost_in_eth = w3_exec.from_wei(gas_cost, 'ether')

    # Calculate the flash loan fee amount
    flash_loan_fee_amount = transaction_value * flash_loan_fee
    total_fees = gas_cost_in_eth + flash_loan_fee_amount

    # Calculate net profit
    net_profit = (raw_profit_percentage / Decimal('100') * transaction_value) - total_fees

    # Calculate profit percentage
    profit_percentage = (net_profit / transaction_value) * Decimal('100')

    return float(profit_percentage)

# Constants for fees (adjust these based on current rates)

GAS_PRICE = Decimal('20')  # Gwei
GAS_LIMIT = Decimal('500000')  # Adjust based on your contract's gas usage
FLASH_LOAN_FEE = Decimal('0.0009')  # 0.09% fee for flash loans

# Calculate gas cost
GAS_COST = w3_exec.to_wei(GAS_PRICE, 'gwei') * GAS_LIMIT

def format_arbitrage_opportunity(config, price_v2, price_v3, fee_tier, profit_percentage):
    """
    Format arbitrage opportunity information in a clear, readable manner.
    """
    v2_price = Decimal(str(price_v2)) if price_v2 is not None else Decimal('0')
    v3_price = Decimal(str(price_v3)) if price_v3 is not None else Decimal('0')
    
    arbitrage_type = "V2 to V3" if v3_price > v2_price else "V3 to V2"
    buy_price = min(v2_price, v3_price)
    sell_price = max(v2_price, v3_price)
    
    output = f"\nArbitrage Opportunity Detected:\n"
    output += f"Pair: {config['name']}\n"
    output += f"Type: {arbitrage_type}\n"
    output += f"Exchange Prices:\n"
    output += f"  Uniswap V2: {v2_price:.8f}\n"
    output += f"  Uniswap V3 ({fee_tier}): {v3_price:.8f}\n"
    output += f"Buy at:  {buy_price:.8f} on {'Uniswap V3' if arbitrage_type == 'V3 to V2' else 'Uniswap V2'}\n"
    output += f"Sell at: {sell_price:.8f} on {'Uniswap V2' if arbitrage_type == 'V3 to V2' else 'Uniswap V3'}\n"
    output += f"Profit Percentage: {profit_percentage:.4f}%\n"
    
    return output

def check_v2_pool_exists(pool_address):
    try:
        v2_pool_contract = w3_local.eth.contract(address=pool_address, abi=V2_POOL_ABI)
        reserves = v2_pool_contract.functions.getReserves().call()
        logging.info(f"V2 Pool {pool_address} exists with reserves: {reserves}")
        return True
    except Exception as e:
        logging.error(f"Error checking V2 pool {pool_address}: {str(e)}")
        return False

def check_v3_pool_liquidity(pool_address):
    v3_pool_contract = w3_local.eth.contract(address=pool_address, abi=V3_POOL_ABI)
    liquidity = v3_pool_contract.functions.liquidity().call()
    logging.info(f"V3 Pool {pool_address} liquidity: {liquidity}")
    return liquidity

def validate_v3_price(price, fee_tier):
    if price is None:
        logging.warning(f"V3 price is None for {fee_tier} fee tier")
        return None
    if price < 1e-10 or price > 1e10:
        logging.warning(f"Unusual V3 price for {fee_tier} fee tier: {price}")
        return None
    return price

def is_valid_arbitrage_opportunity(price_v2, price_v3, profit_percentage):
    if price_v2 is None or price_v3 is None:
        return False
    if price_v2 <= 0 or price_v3 <= 0:
        return False
    if abs(profit_percentage) > 10:  # Adjust this threshold as needed
        logging.warning(f"Unusually high profit percentage: {profit_percentage}%")
        return False
    return True
def monitor_arbitrage_opportunities():
    start_time = time.time()
    last_report_time = start_time
    configurations = load_configurations_from_redis()

    while True:
        current_time = time.time()

        for config_key, config in configurations.items():
            token0_address = config['token0']['address']
            token1_address = config['token1']['address']
            token0_decimals = get_token_decimals(token0_address)
            token1_decimals = get_token_decimals(token1_address)

            if config['v2_pool']:
                v2_pool_contract = w3_local.eth.contract(address=config['v2_pool'], abi=V2_POOL_ABI)
                price_v2 = get_price_v2(v2_pool_contract, token0_decimals, token1_decimals)
            else:
                price_v2 = None

            for fee_tier, pool_info in config['v3_pools'].items():
                v3_pool_contract = w3_local.eth.contract(address=pool_info['address'], abi=V3_POOL_ABI)
                price_v3 = get_price_v3(v3_pool_contract, token0_decimals, token1_decimals)

                if price_v2 is not None and price_v3 is not None:
                    # Calculate profit percentage
                    profit_percentage = calculate_profit_percentage(price_v2, price_v3, GAS_COST, FLASH_LOAN_FEE)

                    if abs(profit_percentage) > DETECTION_THRESHOLD:
                        opportunity_info = format_arbitrage_opportunity(config, price_v2, price_v3, fee_tier, profit_percentage)
                        logging.info(opportunity_info)

                        if abs(profit_percentage) > EXECUTION_THRESHOLD:
                            logging.info(f"Executing arbitrage: {config['name']} - {'V2 to V3' if price_v3 > price_v2 else 'V3 to V2'} ({fee_tier})")
                            execute_arbitrage(config, pool_info, is_v2_to_v3=(price_v3 > price_v2), price_difference=abs(profit_percentage))
                else:
                    logging.warning(f"Unable to calculate prices for {config['name']}: V2 Price = {price_v2}, V3 Price = {price_v3}")

        # Check if it's time to generate a report
        if current_time - last_report_time >= REPORT_INTERVAL:
            generate_report(start_time, current_time)
            last_report_time = current_time
            opportunities.clear()  # Clear opportunities after reporting

        time.sleep(0.1)  # Small delay to prevent overwhelming the system

# Make sure to call this function in your main execution block
def generate_report(start_time, end_time):
    report = f"Arbitrage Opportunity Report\n"
    report += f"Time period: {datetime.fromtimestamp(start_time)} to {datetime.fromtimestamp(end_time)}\n\n"

    if not opportunities:
        report += "No opportunities detected during this period.\n"
    else:
        report += f"Total opportunities detected: {len(opportunities)}\n"
        report += f"Opportunities exceeding execution threshold: {sum(1 for opp in opportunities if opp['profit_percentage'] >= EXECUTION_THRESHOLD * 100)}\n\n"

        report += "Top 10 opportunities:\n"
        top_opportunities = sorted(opportunities, key=lambda x: x['profit_percentage'], reverse=True)[:10]
        for i, opp in enumerate(top_opportunities, 1):
            report += f"{i}. {opp['pair']} - {opp['type']} ({opp['fee_tier']})\n"
            report += f"   Timestamp: {datetime.fromtimestamp(opp['timestamp'])}\n"
            report += f"   V2 Price: {opp['price_v2']:.8f}\n"
            report += f"   V3 Price: {opp['price_v3']:.8f}\n"
            report += f"   Profit %: {opp['profit_percentage']:.2f}%\n\n"

    logging.info("Generating report...")
    logging.info(report)

    # Save report to a file
    with open(f"arbitrage_report_{int(end_time)}.txt", "w") as f:
        f.write(report)

# Replace your existing main execution block with this one
if __name__ == "__main__":
    main_logger.info("Starting multi-pair arbitrage bot with integrated diagnostics...")
    while True:
        try:
            monitor_arbitrage_opportunities()
        except KeyboardInterrupt:
            main_logger.info("Arbitrage bot stopped by user.")
            break
        except Exception as e:
            main_logger.error(f"An error occurred: {str(e)}")
            main_logger.info("Restarting monitoring in 60 seconds...")
            time.sleep(60)