from web3 import Web3
from web3.middleware import geth_poa_middleware
from web3.exceptions import ContractLogicError, BadFunctionCallOutput
from decimal import Decimal
import json
import time
import redis
import logging
from eth_account.messages import encode_defunct
from eth_account import Account
from logging.handlers import RotatingFileHandler

# Initialize logging
logging.basicConfig(level=logging.INFO)
main_logger = logging.getLogger('main_logger')

# Web3 setup
provider_url_localhost = 'http://localhost:8545'
w3_local = Web3(Web3.HTTPProvider(provider_url_localhost))
provider_url_exec = 'http://localhost:8545'
w3_exec = Web3(Web3.HTTPProvider(provider_url_exec))
w3_exec.middleware_onion.inject(geth_poa_middleware, layer=0)

# Wallet and contract details
wallet_address = Web3.to_checksum_address("0x6f2F4f0210AC805D817d4CD0b9A4D0c29d232E93")
private_key = "6575ac283b8aa1cbd913d2d28557e318048f8e62a5a19a74001988e2f40ab06c"

# Constants
UNISWAP_V2_ROUTER_ADDRESS = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
UNISWAP_V3_ROUTER_ADDRESS = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS = "0x26B7B5AB244114ab88578D5C4cD5b096097bf543"
MIN_LIQUIDITY_THRESHOLD_ETH = Decimal('10')
GAS_PRICE = Decimal('20')  # Gwei
GAS_LIMIT = Decimal('500000')
FLASH_LOAN_FEE = Decimal('0.0009')
GAS_COST = w3_exec.to_wei(GAS_PRICE, 'gwei') * GAS_LIMIT

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

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





# Load configurations from Redis
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

# Function to get token decimals
def get_token_decimals(token_address):
    token_contract = w3_local.eth.contract(address=token_address, abi=ERC20_ABI)
    return token_contract.functions.decimals().call()

# Function to get price from V2 pool
def get_price_v2(pool_contract, token0_decimals, token1_decimals):
    try:
        reserves = pool_contract.functions.getReserves().call()
        reserve0 = Decimal(reserves[0])
        reserve1 = Decimal(reserves[1])
        normalized_reserve0 = reserve0 / Decimal(10 ** token0_decimals)
        normalized_reserve1 = reserve1 / Decimal(10 ** token1_decimals)
        price = normalized_reserve1 / normalized_reserve0
        return float(price)
    except Exception as e:
        logging.error(f"Error calculating V2 price: {str(e)}")
        return None

# Function to get price from V3 pool
def get_price_v3(pool_contract, token0_decimals, token1_decimals):
    try:
        liquidity = pool_contract.functions.liquidity().call()
        if Decimal(liquidity) / Decimal(10 ** 18) < MIN_LIQUIDITY_THRESHOLD_ETH:
            return None
        slot0_data = pool_contract.functions.slot0().call()
        sqrt_price_x96 = slot0_data[0]
        sqrt_price = Decimal(sqrt_price_x96) / Decimal(2 ** 96)
        price = sqrt_price ** 2
        decimal_adjustment = Decimal(10 ** (token1_decimals - token0_decimals))
        adjusted_price = price * decimal_adjustment
        return float(adjusted_price)
    except Exception as e:
        logging.error(f"Error getting V3 slot0 data: {str(e)}")
        return None

# Function to check liquidity of V2 pool
def check_v2_pool_liquidity(pool_address):
    try:
        v2_pool_contract = w3_local.eth.contract(address=pool_address, abi=V2_POOL_ABI)
        reserves = v2_pool_contract.functions.getReserves().call()
        reserve0 = Decimal(reserves[0]) / Decimal(10 ** 18)
        reserve1 = Decimal(reserves[1]) / Decimal(10 ** 18)
        if reserve0 >= MIN_LIQUIDITY_THRESHOLD_ETH and reserve1 >= MIN_LIQUIDITY_THRESHOLD_ETH:
            return True
        else:
            return False
    except Exception as e:
        logging.error(f"Error checking V2 pool {pool_address}: {str(e)}")
        return False

# Function to check liquidity of V3 pool
def check_v3_pool_liquidity(pool_address):
    try:
        v3_pool_contract = w3_local.eth.contract(address=pool_address, abi=V3_POOL_ABI)
        liquidity = v3_pool_contract.functions.liquidity().call()
        liquidity_eth = Decimal(liquidity) / Decimal(10 ** 18)
        if liquidity_eth >= MIN_LIQUIDITY_THRESHOLD_ETH:
            return liquidity
        else:
            return 0
    except Exception as e:
        logging.error(f"Error checking V3 pool liquidity {pool_address}: {str(e)}")
        return 0

# Function to calculate profit percentage
def calculate_profit_percentage(price_v2, price_v3, gas_cost, flash_loan_fee):
    price_v2 = Decimal(str(price_v2))
    price_v3 = Decimal(str(price_v3))
    gas_cost = Decimal(str(gas_cost))
    flash_loan_fee = Decimal(str(flash_loan_fee))
    buy_price = min(price_v2, price_v3)
    sell_price = max(price_v2, price_v3)
    raw_profit_percentage = (sell_price - buy_price) / buy_price * Decimal('100')
    transaction_value = buy_price
    gas_cost_in_eth = w3_exec.from_wei(gas_cost, 'ether')
    flash_loan_fee_amount = transaction_value * flash_loan_fee
    total_fees = gas_cost_in_eth + flash_loan_fee_amount
    net_profit = (raw_profit_percentage / Decimal('100') * transaction_value) - total_fees
    profit_percentage = (net_profit / transaction_value) * Decimal('100')
    return float(profit_percentage)

# Function to detect profitable arbitrage opportunity
def detect_profitable_arbitrage_opportunity(configurations):
    best_opportunity = None
    max_profit = -float('inf')
    for config_key, config in configurations.items():
        token0_address = config['token0']['address']
        token1_address = config['token1']['address']
        token0_decimals = get_token_decimals(token0_address)
        token1_decimals = get_token_decimals(token1_address)
        if config.get('v2_pool'):
            v2_pool_contract = w3_local.eth.contract(address=config['v2_pool'], abi=V2_POOL_ABI)
            price_v2 = get_price_v2(v2_pool_contract, token0_decimals, token1_decimals)
            liquidity_v2 = check_v2_pool_liquidity(config['v2_pool'])
        else:
            price_v2, liquidity_v2 = None, 0
        for fee_tier, pool_info in config.get('v3_pools', {}).items():
            v3_pool_contract = w3_local.eth.contract(address=pool_info['address'], abi=V3_POOL_ABI)
            price_v3 = get_price_v3(v3_pool_contract, token0_decimals, token1_decimals)
            liquidity_v3 = check_v3_pool_liquidity(pool_info['address'])
            if price_v2 is not None and price_v3 is not None:
                profit_percentage = calculate_profit_percentage(price_v2, price_v3, GAS_COST, FLASH_LOAN_FEE)
                if profit_percentage > max_profit:
                    max_profit = profit_percentage
                    best_opportunity = {
                        'config': config,
                        'fee_tier': fee_tier,
                        'price_v2': price_v2,
                        'price_v3': price_v3,
                        'liquidity_v2': liquidity_v2,
                        'liquidity_v3': liquidity_v3,
                        'profit_percentage': profit_percentage
                    }
    return best_opportunity

# Main execution
if __name__ == "__main__":
    main_logger.info("Starting arbitrage detection and simulation...")
    configurations = load_and_filter_configurations_from_redis()
    opportunity = detect_profitable_arbitrage_opportunity(configurations)

    if opportunity:
        print("Profitable Arbitrage Opportunity Detected:")
        print(opportunity)
        simulation_result = simulate_arbitrage_execution(opportunity, opportunity['flashloan_amount'])

        if simulation_result:
            print(f"Arbitrage Simulation Result: Start with {simulation_result['initial_amount']} ETH")
            print(f"End with {simulation_result['final_amount']} ETH")
            print(f"Profit: {simulation_result['profit']} ETH")
        else:
            print("Simulation failed.")
    else:
        print("No profitable arbitrage opportunity detected.")