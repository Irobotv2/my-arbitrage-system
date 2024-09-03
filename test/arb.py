import redis
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account import Account
import json
import logging
import time
from decimal import Decimal
from flashbots import flashbot
from eth_account.signers.local import LocalAccount
import uuid

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Setup Web3 connection to Ganache fork
GANACHE_RPC_URL = 'http://localhost:8549'
w3 = Web3(Web3.HTTPProvider(GANACHE_RPC_URL))
w3.middleware_onion.inject(geth_poa_middleware, layer=0)

# Setup Flashbots
FLASHBOTS_RELAY_URL = "https://relay.flashbots.net"  # Use your local Flashbots relay URL

# Generate a new signer account for Flashbots
flashbots_signer: LocalAccount = Account.create()
logging.info(f"Generated Flashbots signer address: {flashbots_signer.address}")

# Setup Flashbots with the new signer
flashbot(w3, flashbots_signer, FLASHBOTS_RELAY_URL)

# Define your wallet address (this should be one of the unlocked accounts in Ganache)
wallet_address = "0x66C2C4152dDc970229938883E2d1527de81afBb8"
private_key = "0x92f8463eb1cb10d0b497c44f5b9ef2dc259992630f5ac44ba881fcafe712b43d"

# Update the contract address with the new one deployed on Ganache
FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS = "0xd14afA25E813eE58AE81Ee0a29BB7e41E7a7e336"

# Define other contract addresses
UNISWAP_V2_ROUTER_ADDRESS = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
UNISWAP_V3_ROUTER_ADDRESS = "0xE592427A0AEce92De3Edee1F18E0157C05861564"

# ABIs
V2_POOL_ABI = [
    {"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"stateMutability":"view","type":"function"},
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
    {"inputs":[],"name":"slot0","outputs":[{"internalType":"uint160","name":"sqrtPriceX96","type":"uint160"},{"internalType":"int24","name":"tick","type":"int24"},{"internalType":"uint16","name":"observationIndex","type":"uint16"},{"internalType":"uint16","name":"observationCardinality","type":"uint16"},{"internalType":"uint16","name":"observationCardinalityNext","type":"uint16"},{"internalType":"uint8","name":"feeProtocol","type":"uint8"},{"internalType":"bool","name":"unlocked","type":"bool"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"liquidity","outputs":[{"internalType":"uint128","name":"","type":"uint128"}],"stateMutability":"view","type":"function"},
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
v2_router_contract = w3.eth.contract(address=UNISWAP_V2_ROUTER_ADDRESS, abi=V2_ROUTER_ABI)
v3_router_contract = w3.eth.contract(address=UNISWAP_V3_ROUTER_ADDRESS, abi=V3_ROUTER_ABI)
flashloan_contract = w3.eth.contract(address=FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS, abi=FLASHLOAN_BUNDLE_EXECUTOR_ABI)

# Constants
EXECUTION_THRESHOLD = 0.02  # 2% threshold for executing arbitrage
USDC_ADDRESS = '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'

def load_configurations_from_redis():
    configs = {}
    for key in redis_client.keys('*_config'):
        config_json = redis_client.get(key)
        config = json.loads(config_json)
        configs[key.decode('utf-8')] = config
    return configs

def get_token_decimals(token_address):
    token_contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
    return token_contract.functions.decimals().call()

def sqrt_price_x96_to_price(sqrt_price_x96, token0_decimals, token1_decimals):
    sqrt_price = Decimal(sqrt_price_x96) / Decimal(2 ** 96)
    price = sqrt_price ** 2
    decimal_adjustment = Decimal(10 ** (token1_decimals - token0_decimals))
    return float(price * decimal_adjustment)

def get_price_v2(pool_contract, token0_decimals, token1_decimals):
    try:
        reserves = pool_contract.functions.getReserves().call()
        reserve0 = Decimal(reserves[0])
        reserve1 = Decimal(reserves[1])
        
        normalized_reserve0 = reserve0 / Decimal(10 ** token0_decimals)
        normalized_reserve1 = reserve1 / Decimal(10 ** token1_decimals)

        return float(normalized_reserve1 / normalized_reserve0)
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

def calculate_arbitrage(price_v2, price_v3):
    if price_v2 > price_v3:
        return (price_v2 / price_v3 - 1) * 100, "V3 to V2"
    else:
        return (price_v3 / price_v2 - 1) * 100, "V2 to V3"

def execute_arbitrage(config, v3_pool_info, direction, price_difference):
    token0_address = config['token0']['address']
    token1_address = config['token1']['address']
    
    # Determine which token is USDC
    if token0_address == USDC_ADDRESS:
        usdc_is_token0 = True
        other_token_address = token1_address
    elif token1_address == USDC_ADDRESS:
        usdc_is_token0 = False
        other_token_address = token0_address
    else:
        logging.error("USDC is not part of this pair")
        return

    # Calculate flash loan amount (use a fraction of the pool's liquidity)
    v3_pool_contract = w3.eth.contract(address=v3_pool_info['address'], abi=V3_POOL_ABI)
    liquidity = v3_pool_contract.functions.liquidity().call()
    flash_loan_amount = int(liquidity * 0.01)  # Use 1% of the pool's liquidity

    deadline = int(time.time()) + 300  # 5 minutes from now

    # Prepare swap parameters
    if direction == "V3 to V2":
        v3_params = {
            'tokenIn': USDC_ADDRESS,
            'tokenOut': other_token_address,
            'fee': v3_pool_info['fee'],
            'recipient': FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS,
            'deadline': deadline,
            'amountIn': flash_loan_amount,
            'amountOutMinimum': 0,
            'sqrtPriceLimitX96': 0
        }
        v3_swap_payload = v3_router_contract.encodeABI(fn_name="exactInputSingle", args=[v3_params])
        
        v2_path = [other_token_address, USDC_ADDRESS]
        v2_swap_payload = v2_router_contract.encodeABI(
            fn_name="swapExactTokensForTokens",
            args=[0, 0, v2_path, FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS, deadline]
        )
    else:  # V2 to V3
        v2_path = [USDC_ADDRESS, other_token_address]
        v2_swap_payload = v2_router_contract.encodeABI(
            fn_name="swapExactTokensForTokens",
            args=[flash_loan_amount, 0, v2_path, FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS, deadline]
        )
        
        v3_params = {
            'tokenIn': other_token_address,
            'tokenOut': USDC_ADDRESS,
            'fee': v3_pool_info['fee'],
            'recipient': FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS,
            'deadline': deadline,
            'amountIn': 0,
            'amountOutMinimum': 0,
            'sqrtPriceLimitX96': 0
        }
        v3_swap_payload = v3_router_contract.encodeABI(fn_name="exactInputSingle", args=[v3_params])

    # Prepare flash loan parameters
    tokens = [USDC_ADDRESS]
    amounts = [flash_loan_amount]
    targets = [UNISWAP_V2_ROUTER_ADDRESS, UNISWAP_V3_ROUTER_ADDRESS]
    payloads = [v2_swap_payload, v3_swap_payload]

    # Execute flash loan
    try:
        nonce = w3.eth.get_transaction_count(wallet_address)
        gas_price = w3.eth.gas_price

        transaction = flashloan_contract.functions.initiateFlashLoanAndBundle(
            tokens, amounts, targets, payloads
        ).build_transaction({
            'from': wallet_address,
            'nonce': nonce,
            'gas': 1000000,  # Adjust as needed
            'gasPrice': gas_price,
        })

        # Sign the transaction
        signed_txn = w3.eth.account.sign_transaction(transaction, private_key=private_key)

        # Create a Flashbots bundle
        bundle = [
            {"signed_transaction": signed_txn.rawTransaction}
        ]

        # Simulate the bundle
        simulation = w3.flashbots.simulate(bundle, block_tag='latest')

        if simulation.get("error"):
            logging.error(f"Bundle simulation failed: {simulation['error']}")
            return

        # Send the bundle
        replacement_uuid = str(uuid.uuid4())
        send_result = w3.flashbots.send_bundle(
            bundle,
            target_block_number=w3.eth.block_number + 1,
            opts={"replacement_uuid": replacement_uuid}
        )

        # Wait for the transaction to be mined
        receipts = send_result.wait()
        if receipts:
            logging.info(f"Arbitrage transaction successful. Gas used: {receipts[0].gasUsed}")
        else:
            logging.error("Arbitrage transaction failed or not mined")

    except Exception as e:
        logging.error(f"Error executing arbitrage: {str(e)}")


def monitor_arbitrage_opportunities():
    configurations = load_configurations_from_redis()

    while True:
        for config_key, config in configurations.items():
            if USDC_ADDRESS not in [config['token0']['address'], config['token1']['address']]:
                continue  # Skip pairs that don't include USDC

            token0_decimals = get_token_decimals(config['token0']['address'])
            token1_decimals = get_token_decimals(config['token1']['address'])

            if config['v2_pool']:
                v2_pool_contract = w3.eth.contract(address=config['v2_pool'], abi=V2_POOL_ABI)
                price_v2 = get_price_v2(v2_pool_contract, token0_decimals, token1_decimals)
            else:
                price_v2 = None

            for fee_tier, pool_info in config['v3_pools'].items():
                v3_pool_contract = w3.eth.contract(address=pool_info['address'], abi=V3_POOL_ABI)
                price_v3 = get_price_v3(v3_pool_contract, token0_decimals, token1_decimals)

                if price_v2 is not None and price_v3 is not None:
                    price_difference, direction = calculate_arbitrage(price_v2, price_v3)

                    if price_difference >= EXECUTION_THRESHOLD:
                        logging.info(f"Arbitrage opportunity detected for {config['name']}:")
                        logging.info(f"V2 Price: {price_v2}")
                        logging.info(f"V3 Price ({fee_tier}): {price_v3}")
                        logging.info(f"Price difference: {price_difference:.2f}%")
                        logging.info(f"Direction: {direction}")

                        execute_arbitrage(config, pool_info, direction, price_difference)

        time.sleep(10)  # Wait for 10 seconds before the next iteration
if __name__ == "__main__":
    logging.info("Starting arbitrage monitoring on Ganache fork...")
    monitor_arbitrage_opportunities()