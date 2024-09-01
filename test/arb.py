from web3 import Web3
from web3.middleware import geth_poa_middleware
import redis
import json
import time
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler

# Initialize Web3
provider_url_exec = 'https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c'
w3_exec = Web3(Web3.HTTPProvider(provider_url_exec))
w3_exec.middleware_onion.inject(geth_poa_middleware, layer=0)

# Define your wallet address and private key
wallet_address = "0x19F5034FAB7e2CcA2Ad46EC28acF20cbd098D3fF"
private_key = "6d0ad7f50dccb88715e3592f39ea5be4c715531223b2daeb2de621dc8f6c230f"

# Define contract addresses
FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS = "0x26B7B5AB244114ab88578D5C4cD5b096097bf543"
UNISWAP_V2_ROUTER_ADDRESS = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
UNISWAP_V3_ROUTER_ADDRESS = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
WETH_ADDRESS = '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'

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
flashloan_contract = w3_exec.eth.contract(address=FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS, abi=FLASHLOAN_BUNDLE_EXECUTOR_ABI)
v2_router_contract = w3_exec.eth.contract(address=UNISWAP_V2_ROUTER_ADDRESS, abi=V2_ROUTER_ABI)
v3_router_contract = w3_exec.eth.contract(address=UNISWAP_V3_ROUTER_ADDRESS, abi=V3_ROUTER_ABI)

# Initialize logging
logging.basicConfig(level=logging.INFO)
main_logger = logging.getLogger('main_logger')

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Global variables
DETECTION_THRESHOLD = 0.005  # 0.5% threshold for detecting opportunities
EXECUTION_THRESHOLD = 0.01   # 1% threshold for executing arbitrage

def load_configurations_from_redis():
    configs = {}
    for key in redis_client.keys('*_config'):
        config_json = redis_client.get(key)
        config = json.loads(config_json)
        configs[key.decode('utf-8')] = config
    return configs

def get_token_decimals(token_address):
    token_contract = w3_exec.eth.contract(address=token_address, abi=ERC20_ABI)
    return token_contract.functions.decimals().call()

def sqrt_price_x96_to_price(sqrt_price_x96, token0_decimals, token1_decimals):
    price = (sqrt_price_x96 ** 2) / (2 ** 192)
    decimal_adjustment = 10 ** (token1_decimals - token0_decimals)
    return price * decimal_adjustment

def get_price_v2(pool_contract, token0_decimals, token1_decimals):
    reserves = pool_contract.functions.getReserves().call()
    reserve0 = reserves[0]
    reserve1 = reserves[1]
    
    normalized_reserve0 = reserve0 / (10 ** token0_decimals)
    normalized_reserve1 = reserve1 / (10 ** token1_decimals)

    return normalized_reserve1 / normalized_reserve0

def get_price_v3(pool_contract, token0_decimals, token1_decimals):
    slot0_data = pool_contract.functions.slot0().call()
    sqrt_price_x96 = slot0_data[0]
    return sqrt_price_x96_to_price(sqrt_price_x96, token0_decimals, token1_decimals)

def sort_tokens(token_a, token_b):
    return (token_a, token_b) if token_a.lower() < token_b.lower() else (token_b, token_a)

def execute_arbitrage(config, v3_pool_info, is_v2_to_v3, flash_loan_amount):
    token0_address = config['token0']['address']
    token1_address = config['token1']['address']
    
    sorted_tokens = sort_tokens(token0_address, token1_address)
    slippage = 0.005
    min_amount_out = int(flash_loan_amount * (1 - slippage))
    deadline = int(time.time()) + 60 * 2  # 2-minute deadline

    if is_v2_to_v3:
        targets = [UNISWAP_V2_ROUTER_ADDRESS, UNISWAP_V3_ROUTER_ADDRESS]
        
        v2_swap_payload = v2_router_contract.encodeABI(
            fn_name="swapExactTokensForTokens",
            args=[
                flash_loan_amount, 
                min_amount_out,
                sorted_tokens, 
                FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS,
                deadline
            ]
        )
        
        v3_swap_payload = v3_router_contract.encodeABI(
            fn_name="exactInputSingle",
            args=[{
                'tokenIn': sorted_tokens[1],
                'tokenOut': sorted_tokens[0],
                'fee': v3_pool_info['fee'],
                'recipient': FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS,
                'deadline': deadline,
                'amountIn': flash_loan_amount,
                'amountOutMinimum': min_amount_out,
                'sqrtPriceLimitX96': 0,
            }]
        )

        payloads = [v2_swap_payload, v3_swap_payload]

    else:
        targets = [UNISWAP_V3_ROUTER_ADDRESS, UNISWAP_V2_ROUTER_ADDRESS]
        
        v3_swap_payload = v3_router_contract.encodeABI(
            fn_name="exactInputSingle",
            args=[{
                'tokenIn': sorted_tokens[0],
                'tokenOut': sorted_tokens[1],
                'fee': v3_pool_info['fee'],
                'recipient': FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS,
                'deadline': deadline,
                'amountIn': flash_loan_amount,
                'amountOutMinimum': min_amount_out,
                'sqrtPriceLimitX96': 0,
            }]
        )
        
        v2_swap_payload = v2_router_contract.encodeABI(
            fn_name="swapExactTokensForTokens",
            args=[
                flash_loan_amount, 
                min_amount_out,
                list(reversed(sorted_tokens)),
                FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS,
                deadline
            ]
        )

        payloads = [v3_swap_payload, v2_swap_payload]

    try:
        # Build and execute the flashloan with bundled operations
        nonce = w3_exec.eth.get_transaction_count(wallet_address)
        transaction = flashloan_contract.functions.initiateFlashLoanAndBundle(
            [token0_address], [flash_loan_amount], targets, payloads
        ).build_transaction({
            'from': wallet_address,
            'nonce': nonce,
            'gas': 3000000,
            'gasPrice': w3_exec.to_wei('20', 'gwei')
        })

        signed_tx = w3_exec.eth.account.sign_transaction(transaction, private_key=private_key)
        tx_hash = w3_exec.eth.send_raw_transaction(signed_tx.rawTransaction)

        main_logger.info(f"Arbitrage transaction sent. Hash: {tx_hash.hex()}")
        
        # Wait for the transaction receipt
        receipt = w3_exec.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status == 1:
            main_logger.info(f"Arbitrage transaction confirmed. Hash: {tx_hash.hex()}")
        else:
            main_logger.error("Arbitrage execution failed.")

    except Exception as e:
        main_logger.error(f"Error executing flashloan arbitrage: {str(e)}", exc_info=True)

def monitor_arbitrage_opportunities():
    configurations = load_configurations_from_redis()

    while True:
        for config_key, config in configurations.items():
            token0_address = config['token0']['address']
            token1_address = config['token1']['address']
            token0_decimals = get_token_decimals(token0_address)
            token1_decimals = get_token_decimals(token1_address)

            if config['v2_pool']:
                v2_pool_contract = w3_exec.eth.contract(address=config['v2_pool'], abi=V2_POOL_ABI)
                price_v2 = get_price_v2(v2_pool_contract, token0_decimals, token1_decimals)
            else:
                price_v2 = None

            for fee_tier, pool_info in config['v3_pools'].items():
                v3_pool_contract = w3_exec.eth.contract(address=pool_info['address'], abi=V3_POOL_ABI)
                price_v3 = get_price_v3(v3_pool_contract, token0_decimals, token1_decimals)

                logging.info(f"{config['name']} - Uniswap V2 Price: {price_v2}")
                logging.info(f"{config['name']} - Uniswap V3 ({fee_tier}) Price: {price_v3}")

                if price_v2:
                    if price_v3 > price_v2 * (1 + DETECTION_THRESHOLD):
                        price_difference = (price_v3 / price_v2 - 1) * 100
                        if price_v3 > price_v2 * (1 + EXECUTION_THRESHOLD):
                            logging.info(f"Executing arbitrage: {config['name']} - Uniswap V2 to Uniswap V3 ({fee_tier})")
                            execute_arbitrage(config, pool_info, is_v2_to_v3=True, flash_loan_amount=w3_exec.to_wei(3700, 'ether'))

                    elif price_v2 > price_v3 * (1 + DETECTION_THRESHOLD):
                        price_difference = (price_v2 / price_v3 - 1) * 100
                        if price_v2 > price_v3 * (1 + EXECUTION_THRESHOLD):
                            logging.info(f"Executing arbitrage: {config['name']} - Uniswap V3 ({fee_tier}) to Uniswap V2")
                            execute_arbitrage(config, pool_info, is_v2_to_v3=False, flash_loan_amount=w3_exec.to_wei(3700, 'ether'))

        time.sleep(0.1)  # Small delay to prevent overwhelming the system

# Main execution block
if __name__ == "__main__":
    main_logger.info("Starting multi-pair arbitrage bot with flashloaning...")
    
    try:
        monitor_arbitrage_opportunities()
    except KeyboardInterrupt:
        main_logger.info("Arbitrage bot stopped by user.")
    except Exception as e:
        main_logger.error(f"An error occurred: {str(e)}")
