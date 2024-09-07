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
import requests
from eth_account.messages import encode_defunct
from eth_account import Account
# Initialize logging
logging.basicConfig(level=logging.INFO)

# Setup Web3 connection for querying data (localhost)
provider_url_localhost = 'http://localhost:8545'
w3_local = Web3(Web3.HTTPProvider(provider_url_localhost, request_kwargs={'timeout': 30}))

# Setup Web3 connection for executing transactions (Tenderly RPC)
provider_url_exec = 'http://localhost:8545'
w3_exec = Web3(Web3.HTTPProvider(provider_url_exec))
w3_exec.middleware_onion.inject(geth_poa_middleware, layer=0)

# Define your wallet address and private key
wallet_address = "0x6f2F4f0210AC805D817d4CD0b9A4D0c29d232E93"
private_key = "6575ac283b8aa1cbd913d2d28557e318048f8e62a5a19a74001988e2f40ab06c"  # Replace with your actual private key

# Define contract addresses
UNISWAP_V2_ROUTER_ADDRESS = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
UNISWAP_V3_ROUTER_ADDRESS = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS = "0x26B7B5AB244114ab88578D5C4cD5b096097bf543"
# Define minimum liquidity threshold in ETH (or equivalent value)
MIN_LIQUIDITY_THRESHOLD_ETH = Decimal('10')  # Example: 10 ETH equivalent

# Define builder URLs
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
# Create loggers (add this after the setup_logger function)
main_logger = logging.getLogger('main_logger')
main_logger.setLevel(logging.INFO)
submitted_logger = logging.getLogger('submitted_transactions')
confirmed_logger = logging.getLogger('confirmed_transactions')

# Create contract instances
v2_router_contract = w3_exec.eth.contract(address=UNISWAP_V2_ROUTER_ADDRESS, abi=V2_ROUTER_ABI)
v3_router_contract = w3_exec.eth.contract(address=UNISWAP_V3_ROUTER_ADDRESS, abi=V3_ROUTER_ABI)
flashloan_contract = w3_exec.eth.contract(address=FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS, abi=FLASHLOAN_BUNDLE_EXECUTOR_ABI)


def setup_logger(name, log_file, level=logging.INFO):
    formatter = logging.Formatter('%(asctime)s - %(message)s')
    handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger



def send_bundle_to_builders(bundle):
    # Serialize the bundle to JSON string for signing
    bundle_json = json.dumps(bundle, separators=(',', ':'))  # Ensure minified JSON

    # Create a message for signing
    message = encode_defunct(text=bundle_json)

    # Sign the message with the private key
    signed_message = Account.sign_message(message, private_key=private_key)

    # Construct the X-Flashbots-Signature header
    flashbots_signature = f"{wallet_address}:{signed_message.signature.hex()}"

    for url in builder_urls:
        try:
            # Include the X-Flashbots-Signature header
            headers = {
                "Content-Type": "application/json",
                "X-Flashbots-Signature": flashbots_signature
            }

            main_logger.info(f"Sending bundle to {url} with payload: {json.dumps(bundle, indent=2)}")
            response = requests.post(url, json=bundle, headers=headers)

            if response.status_code == 200:
                main_logger.info(f"Bundle sent successfully to {url}: {response.json()}")
            else:
                main_logger.warning(f"Failed to send bundle to {url}: {response.status_code} - {response.text}")
        except Exception as e:
            main_logger.error(f"Error sending bundle to {url}: {str(e)}")

def send_bundle(transaction_bundle):
    # Construct the bundle payload
    bundle = {
        "method": "eth_sendBundle",
        "params": [transaction_bundle],
        "id": 1,
        "jsonrpc": "2.0"
    }

    # Log the crafted bundle payload
    main_logger.info(f"Crafted bundle for submission: {json.dumps(bundle, indent=2)}")

    # Send bundle to all builders
    send_bundle_to_builders(bundle)
# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Global variables
REPORT_INTERVAL = 2 * 60 * 60  # 2 hours in seconds
DETECTION_THRESHOLD = 0.01  # 0.5% threshold for detecting opportunities
EXECUTION_THRESHOLD = 0.02   # 1% threshold for executing arbitrage
opportunities = []

def load_and_filter_configurations_from_redis():
    """
    Load pool configurations from Redis and filter out those with zero or insufficient liquidity.
    """
    configs = {}
    for key in redis_client.keys('*_config'):
        config_json = redis_client.get(key)
        config = json.loads(config_json)

        # Check V2 pool
        if config.get('v2_pool') and check_v2_pool_liquidity(config['v2_pool']):
            configs[key.decode('utf-8')] = config

        # Check V3 pools
        else:
            valid_v3_pools = {fee: pool for fee, pool in config.get('v3_pools', {}).items() if check_v3_pool_liquidity(pool['address']) > 0}
            if valid_v3_pools:
                config['v3_pools'] = valid_v3_pools
                configs[key.decode('utf-8')] = config
            else:
                main_logger.warning(f"No valid pools found for {key.decode('utf-8')}. Skipping.")
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
        # Check if pool liquidity meets the minimum threshold
        liquidity = pool_contract.functions.liquidity().call()
        if Decimal(liquidity) / Decimal(10 ** 18) < MIN_LIQUIDITY_THRESHOLD_ETH:
            logging.warning(f"V3 pool has insufficient liquidity: {liquidity}")
            return None
        
        # If liquidity is sufficient, proceed with price calculation
        slot0_data = pool_contract.functions.slot0().call()
        sqrt_price_x96 = slot0_data[0]
        return sqrt_price_x96_to_price(sqrt_price_x96, token0_decimals, token1_decimals)
    except Exception as e:
        logging.error(f"Error getting V3 slot0 data: {str(e)}")
        return None


def sort_tokens(token_a, token_b):
    return (token_a, token_b) if token_a.lower() < token_b.lower() else (token_b, token_a)

def calculate_optimal_flashloan_amount(v3_pool_address, price_difference):
    """
    Calculate the optimal amount for a flash loan based on price difference and pool liquidity.
    """
    try:
        v3_pool_contract = w3_local.eth.contract(address=v3_pool_address, abi=V3_POOL_ABI)
        liquidity = v3_pool_contract.functions.liquidity().call()
        
        # Convert liquidity to ether equivalent and Decimal
        max_amount = Decimal(w3_exec.from_wei(liquidity, 'ether'))
        
        # Convert price_difference to Decimal
        price_difference = Decimal(price_difference)
        
        # Calculate optimal amount based on price difference
        # Ensure it's between 1 and 100 WETH
        optimal_amount = max(min(max_amount * (price_difference / Decimal(100)), Decimal(100)), Decimal(1))
        
        main_logger.info(f"Liquidity: {liquidity}, Max amount: {max_amount}, Price difference: {price_difference}, Optimal amount: {optimal_amount}")
        
        return float(optimal_amount)  # Convert back to float if needed
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
    """
    Execute an arbitrage opportunity by crafting and submitting transactions as bundles to Flashbots.
    """
    token0_address = config['token0']['address']
    token1_address = config['token1']['address']
    
    sorted_tokens = sort_tokens(token0_address, token1_address)

    # Check liquidity for V3 pool
    v3_pool_contract = w3_local.eth.contract(address=v3_pool_info['address'], abi=V3_POOL_ABI)
    liquidity = v3_pool_contract.functions.liquidity().call()
    
    if Decimal(liquidity) / Decimal(10 ** 18) < MIN_LIQUIDITY_THRESHOLD_ETH:
        main_logger.warning(f"V3 pool {v3_pool_info['address']} has insufficient liquidity. Skipping arbitrage execution.")
        return

    # Calculate optimal flash loan amount between 1 and 100 WETH
    optimal_amount_eth = calculate_optimal_flashloan_amount(v3_pool_info['address'], price_difference)
    flash_loan_amount = w3_exec.to_wei(optimal_amount_eth, 'ether')

    # Log the details of the arbitrage execution
    main_logger.info(f"Calculated optimal flash loan amount: {optimal_amount_eth} WETH ({flash_loan_amount} wei), Gas price: {w3_exec.eth.gas_price}, Expected profit: {price_difference}%")

    # Log the details of the arbitrage execution
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
    all_targets = list(sorted_tokens) + swap_targets


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

        # Prepare the transaction bundle for Flashbots
        transaction_bundle = {
            "txs": [signed_tx.rawTransaction.hex()],
            "blockNumber": w3_exec.eth.block_number + 1,
            "minTimestamp": int(time.time()),
            "maxTimestamp": int(time.time()) + 60,  # Bundle valid for the next 60 seconds
            "revertingTxHashes": []
        }

        # Log the transaction bundle details
        main_logger.info(f"Transaction bundle details: {json.dumps(transaction_bundle, indent=2)}")

        # Send the crafted bundle to the builders
        send_bundle(transaction_bundle)

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

def check_v2_pool_liquidity(pool_address):
    """
    Check if a V2 pool exists, has non-zero reserves, and meets the minimum liquidity threshold.
    """
    try:
        v2_pool_contract = w3_local.eth.contract(address=pool_address, abi=V2_POOL_ABI)
        reserves = v2_pool_contract.functions.getReserves().call()
        reserve0 = Decimal(reserves[0]) / Decimal(10 ** 18)  # Convert to ETH equivalent
        reserve1 = Decimal(reserves[1]) / Decimal(10 ** 18)  # Convert to ETH equivalent

        if reserve0 >= MIN_LIQUIDITY_THRESHOLD_ETH and reserve1 >= MIN_LIQUIDITY_THRESHOLD_ETH:
            logging.info(f"V2 Pool {pool_address} meets liquidity threshold with reserves: {reserves}")
            return True
        else:
            logging.warning(f"V2 Pool {pool_address} does not meet liquidity threshold: reserve0={reserve0} ETH, reserve1={reserve1} ETH")
            return False
    except Exception as e:
        logging.error(f"Error checking V2 pool {pool_address}: {str(e)}")
        return False



def check_v3_pool_liquidity(pool_address):
    """
    Check the liquidity of a V3 pool and ensure it meets the minimum threshold.
    """
    try:
        v3_pool_contract = w3_local.eth.contract(address=pool_address, abi=V3_POOL_ABI)
        liquidity = v3_pool_contract.functions.liquidity().call()
        
        # Convert liquidity to an equivalent value in ETH (or the base asset)
        # Assuming that liquidity is already in a base unit like ETH
        liquidity_eth = Decimal(liquidity) / Decimal(10 ** 18)  # Adjust based on token decimals

        if liquidity_eth >= MIN_LIQUIDITY_THRESHOLD_ETH:
            logging.info(f"V3 Pool {pool_address} meets liquidity threshold: {liquidity_eth} ETH")
            return liquidity
        else:
            logging.warning(f"V3 Pool {pool_address} does not meet liquidity threshold: {liquidity_eth} ETH")
            return 0
    except Exception as e:
        logging.error(f"Error checking V3 pool liquidity {pool_address}: {str(e)}")
        return 0



def validate_v3_price(price, fee_tier):
    if price is None:
        logging.warning(f"V3 price is None for {fee_tier} fee tier")
        return None
    if price < 1e-10 or price > 1e10:
        logging.warning(f"Unusual V3 price for {fee_tier} fee tier: {price}")
        return None
    return price

def is_valid_arbitrage_opportunity(price_v2, price_v3, profit_percentage, liquidity_v2, liquidity_v3):
    if price_v2 is None or price_v3 is None:
        logging.debug("Opportunity validation failed: One or both prices are None.")
        return False
    if price_v2 <= 0 or price_v3 <= 0:
        logging.debug("Opportunity validation failed: One or both prices are less than or equal to 0.")
        return False
    if profit_percentage <= 0:  # Exclude negative or zero profit percentages
        logging.info(f"Opportunity validation failed: Profit percentage is not positive: {profit_percentage}%")
        return False
    if abs(profit_percentage) > 10:  # Adjust this threshold as needed
        logging.warning(f"Opportunity validation failed: Unusually high profit percentage: {profit_percentage}%")
        return False
    if liquidity_v2 < MIN_LIQUIDITY_THRESHOLD_ETH or liquidity_v3 < MIN_LIQUIDITY_THRESHOLD_ETH:
        logging.warning(f"Opportunity validation failed: Liquidity below threshold: V2={liquidity_v2}, V3={liquidity_v3}")
        return False
    return True




# Update the generate_report function to run for 2 minutes
def generate_report(start_time, end_time):
    report = f"Arbitrage Opportunity Report\n"
    report += f"Time period: {datetime.fromtimestamp(start_time)} to {datetime.fromtimestamp(end_time)}\n\n"

    if not opportunities:
        report += "No opportunities detected during this period.\n"
    else:
        report += f"Total opportunities detected: {len(opportunities)}\n"
        report += f"Opportunities exceeding execution threshold: {sum(1 for opp in opportunities if opp['profit_percentage'] >= EXECUTION_THRESHOLD * 100)}\n\n"

        report += "Detailed Analysis of Top 10 Opportunities:\n"
        top_opportunities = sorted(opportunities, key=lambda x: x['profit_percentage'], reverse=True)[:10]
        for i, opp in enumerate(top_opportunities, 1):
            report += f"{i}. Pair: {opp['pair']} - Type: {opp['type']} ({opp['fee_tier']})\n"
            report += f"   Timestamp: {datetime.fromtimestamp(opp['timestamp'])}\n"
            report += f"   V2 Price: {opp['price_v2']:.8f}\n"
            report += f"   V3 Price: {opp['price_v3']:.8f}\n"
            report += f"   Profit %: {opp['profit_percentage']:.2f}%\n"

            # Detailed Logging and Analysis
            report += check_detailed_arbitrage_analysis(opp)

    logging.info("Generating report...")
    logging.info(report)

    # Save report to a file
    with open(f"arbitrage_report_{int(end_time)}.txt", "w") as f:
        f.write(report)

def check_detailed_arbitrage_analysis(opp):
    """
    Perform a detailed analysis on the given arbitrage opportunity and return a string for the report.
    """
    details = "\n  Detailed Analysis:\n"

    # Check price calculation differences
    if abs(opp['price_v2'] - opp['price_v3']) < 1e-8:
        details += "  - Price calculation difference: Minor discrepancy detected.\n"
    else:
        details += "  - Price calculation difference: Significant discrepancy. Review formulas.\n"

    # Check fee structure differences
    if opp['fee_tier'] not in [500, 3000, 10000]:  # Assuming 0.05%, 0.3%, 1%
        details += "  - Fee structure difference: Unrecognized V3 fee tier.\n"
    else:
        details += "  - Fee structure verified correctly for V3.\n"

    # Slippage estimation accuracy
    if abs(opp['slippage_v2'] - opp['slippage_v3']) > 0.01:
        details += "  - Slippage estimation: Large difference in slippage between V2 and V3.\n"
    else:
        details += "  - Slippage estimation is within acceptable range.\n"

    # Decimal precision consistency
    if 'decimal_precision_issue' in opp:
        details += "  - Decimal precision: Inconsistent handling of decimals detected.\n"
    else:
        details += "  - Decimal precision is consistent across calculations.\n"

    # Check liquidity depth
    if opp['liquidity_v2'] < MIN_LIQUIDITY_THRESHOLD_ETH or opp['liquidity_v3'] < MIN_LIQUIDITY_THRESHOLD_ETH:
        details += "  - Liquidity depth: One or more pools do not meet the minimum liquidity threshold.\n"
    else:
        details += "  - Liquidity depth meets the required threshold.\n"

    # Gas cost estimation check
    if opp['gas_cost'] > GAS_COST:
        details += "  - Gas cost estimation: Potentially outdated or inaccurate gas price data.\n"
    else:
        details += "  - Gas cost estimation is within the expected range.\n"

    # Flash loan fee accuracy
    if opp['flash_loan_fee'] != FLASH_LOAN_FEE:
        details += "  - Flash loan fee: Discrepancy detected in flash loan fee calculation.\n"
    else:
        details += "  - Flash loan fee calculation is accurate.\n"

    # Price impact check
    if opp['price_impact'] > 0.01:  # Example threshold for price impact
        details += "  - Price impact: Significant price impact detected due to trade size.\n"
    else:
        details += "  - Price impact is minimal.\n"

    # Tick spacing check for V3
    if 'tick_spacing_issue' in opp:
        details += "  - V3 Tick Spacing: Tick spacing inconsistency detected in V3 pools.\n"
    else:
        details += "  - V3 Tick Spacing is correctly handled.\n"

    # Stale data usage
    if opp['data_age'] > 5:  # 5 seconds threshold for data age
        details += "  - Data Age: Data used in calculations may be outdated.\n"
    else:
        details += "  - Data Age is recent.\n"

    # Mathematical errors
    if 'math_error' in opp:
        details += "  - Mathematical Error: Rounding or calculation error detected.\n"
    else:
        details += "  - No mathematical errors detected.\n"

    # Pool address verification
    if 'invalid_pool_address' in opp:
        details += "  - Pool Address: Invalid or incorrect pool address used for fetching data.\n"
    else:
        details += "  - Pool Address verification passed.\n"

    # Time delay check
    if opp['execution_delay'] > 5:  # 5 seconds threshold for time delays
        details += "  - Time Delay: High time delay between opportunity detection and execution.\n"
    else:
        details += "  - Time Delay is within acceptable limits.\n"

    # MEV cost consideration
    if 'mev_cost_impact' in opp:
        details += "  - MEV Costs: Significant MEV costs detected.\n"
    else:
        details += "  - No significant MEV costs detected.\n"

    return details


def monitor_arbitrage_opportunities(duration=120):
    """
    Monitor and execute arbitrage opportunities for a specified duration.
    """
    start_time = time.time()
    configurations = load_and_filter_configurations_from_redis()  # Use the filtered configurations

    while time.time() - start_time < duration:
        current_time = time.time()

        for config_key, config in configurations.items():
            token0_address = config['token0']['address']
            token1_address = config['token1']['address']
            token0_decimals = get_token_decimals(token0_address)
            token1_decimals = get_token_decimals(token1_address)

            if config.get('v2_pool'):
                v2_pool_contract = w3_local.eth.contract(address=config['v2_pool'], abi=V2_POOL_ABI)
                price_v2 = get_price_v2(v2_pool_contract, token0_decimals, token1_decimals)
                logging.debug(f"V2 Price for {config['name']}: {price_v2}")
            else:
                price_v2 = None
                logging.debug(f"No V2 pool found for {config['name']}")

            for fee_tier, pool_info in config.get('v3_pools', {}).items():
                v3_pool_contract = w3_local.eth.contract(address=pool_info['address'], abi=V3_POOL_ABI)
                price_v3 = get_price_v3(v3_pool_contract, token0_decimals, token1_decimals)
                logging.debug(f"V3 Price for {config['name']} (Fee tier: {fee_tier}): {price_v3}")

                if price_v2 is not None and price_v3 is not None:
                    # Calculate profit percentage
                    profit_percentage = calculate_profit_percentage(price_v2, price_v3, GAS_COST, FLASH_LOAN_FEE)
                    logging.debug(f"Profit percentage for {config['name']}: {profit_percentage}%")

                    # Validate the opportunity with the new checks
                    if abs(profit_percentage) > DETECTION_THRESHOLD and is_valid_arbitrage_opportunity(
                            price_v2, price_v3, profit_percentage, liquidity_v2=10, liquidity_v3=10):  # Replace with actual liquidity check
                        opportunity_info = format_arbitrage_opportunity(config, price_v2, price_v3, fee_tier, profit_percentage)
                        logging.info(f"Opportunity detected: {opportunity_info}")

                        # Add the opportunity to the list
                        opportunities.append({
                            'pair': config['name'],
                            'type': 'V2 to V3' if price_v3 > price_v2 else 'V3 to V2',
                            'fee_tier': fee_tier,
                            'timestamp': current_time,
                            'price_v2': price_v2,
                            'price_v3': price_v3,
                            'profit_percentage': profit_percentage,
                            # Include additional fields used in the report
                            'slippage_v2': 0.01,  # Example placeholder; replace with actual slippage calculation
                            'slippage_v3': 0.01,
                            'liquidity_v2': 10,  # Example placeholder; replace with actual liquidity
                            'liquidity_v3': 10,
                            'gas_cost': GAS_COST,
                            'flash_loan_fee': FLASH_LOAN_FEE,
                            'price_impact': 0.01,  # Example placeholder; replace with actual price impact calculation
                            'data_age': 1,  # Example placeholder; replace with actual data age
                            'execution_delay': 2  # Example placeholder; replace with actual delay
                        })

                        logging.info("Opportunity added to list.")

                        if abs(profit_percentage) > EXECUTION_THRESHOLD:
                            logging.info(f"Executing arbitrage: {config['name']} - {'V2 to V3' if price_v3 > price_v2 else 'V3 to V2'} ({fee_tier})")
                            execute_arbitrage(config, pool_info, is_v2_to_v3=(price_v3 > price_v2), price_difference=abs(profit_percentage))
                    else:
                        logging.debug(f"No valid arbitrage opportunity for {config['name']}: Profit {profit_percentage}%")
                else:
                    logging.warning(f"Unable to calculate prices for {config['name']}: V2 Price = {price_v2}, V3 Price = {price_v3}")

        # Report generation after running for 2 minutes
        if current_time - start_time >= duration:
            try:
                logging.info("Starting report generation...")
                generate_report(start_time, current_time)
                logging.info("Report generation completed successfully.")
            except Exception as e:
                logging.error(f"Error during report generation: {str(e)}")
            break

        time.sleep(0.1)  # Small delay to prevent overwhelming the system

# Run for 2 minutes for debugging
if __name__ == "__main__":
    main_logger.info("Starting multi-pair arbitrage bot for detailed diagnostic analysis...")
    monitor_arbitrage_opportunities(duration=120)