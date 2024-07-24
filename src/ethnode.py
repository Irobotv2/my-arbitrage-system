import time
from web3 import Web3
from datetime import datetime
import json
from decimal import Decimal
import logging
from web3.exceptions import Web3Exception

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ethereum node URL
ETH_NODE_URL = "https://mainnet.infura.io/v3/0640f56f05a942d7a25cfeff50de344d"

# Web3 instance
w3 = Web3(Web3.HTTPProvider(ETH_NODE_URL))

# Contract addresses
WETH_ADDRESS = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
USDC_ADDRESS = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
UNISWAP_V2_PAIR_ADDRESS = "0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc"
UNISWAP_V3_POOL_ADDRESS = "0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8"

# ABI (Application Binary Interface) for the contracts
UNISWAP_V2_PAIR_ABI = [{"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"stateMutability":"view","type":"function"}]
UNISWAP_V3_POOL_ABI = [{"inputs":[],"name":"slot0","outputs":[{"internalType":"uint160","name":"sqrtPriceX96","type":"uint160"},{"internalType":"int24","name":"tick","type":"int24"},{"internalType":"uint16","name":"observationIndex","type":"uint16"},{"internalType":"uint16","name":"observationCardinality","type":"uint16"},{"internalType":"uint16","name":"observationCardinalityNext","type":"uint16"},{"internalType":"uint8","name":"feeProtocol","type":"uint8"},{"internalType":"bool","name":"unlocked","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"liquidity","outputs":[{"internalType":"uint128","name":"","type":"uint128"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"fee","outputs":[{"internalType":"uint24","name":"","type":"uint24"}],"stateMutability":"view","type":"function"}]

# Contract instances
uniswap_v2_pair = w3.eth.contract(address=UNISWAP_V2_PAIR_ADDRESS, abi=UNISWAP_V2_PAIR_ABI)
uniswap_v3_pool = w3.eth.contract(address=UNISWAP_V3_POOL_ADDRESS, abi=UNISWAP_V3_POOL_ABI)

def retry_call(func, max_attempts=3, delay=1):
    for attempt in range(max_attempts):
        try:
            return func()
        except Web3Exception as e:
            if attempt == max_attempts - 1:
                raise
            logger.error(f"Error: {e}. Retrying in {delay} seconds...")
            time.sleep(delay)

def query_uniswap_v2():
    reserves = retry_call(lambda: uniswap_v2_pair.functions.getReserves().call())
    return {
        'reserve0': reserves[0],
        'reserve1': reserves[1]
    }

def query_uniswap_v3():
    slot0 = retry_call(lambda: uniswap_v3_pool.functions.slot0().call())
    liquidity = retry_call(lambda: uniswap_v3_pool.functions.liquidity().call())
    fee = retry_call(lambda: uniswap_v3_pool.functions.fee().call())
    return {
        'sqrtPriceX96': slot0[0],
        'liquidity': liquidity,
        'feeTier': fee
    }
def calculate_v2_price(reserve0, reserve1):
    return (Decimal(reserve1) / Decimal(10**6)) / (Decimal(reserve0) / Decimal(10**18))

def calculate_v3_price(sqrtPriceX96):
    price = (Decimal(sqrtPriceX96) / Decimal(2**96)) ** 2
    return price * Decimal(10**12) / Decimal(10**6)  # Adjust for USDC decimals
def validate_price(price, min_price=2000, max_price=4000):
    return min_price <= price <= max_price
def calculate_optimal_flash_loan(v2_price, v3_price, max_amount=100):
    price_diff = abs(v2_price - v3_price)
    return min(Decimal(max_amount), Decimal(price_diff * 1000))

def calculate_arbitrage(v2_data, v3_data):
    v2_price = calculate_v2_price(v2_data['reserve0'], v2_data['reserve1'])
    v3_price = calculate_v3_price(v3_data['sqrtPriceX96'])

    logger.info(f"Calculated V2 Price (USDC per WETH): {v2_price}")
    logger.info(f"Calculated V3 Price (USDC per WETH): {v3_price}")

    if not (validate_price(v2_price) and validate_price(v3_price)):
        logger.error(f"Invalid prices: V2={v2_price}, V3={v3_price}")
        logger.info(f"V2 data: reserve0={v2_data['reserve0']}, reserve1={v2_data['reserve1']}")
        logger.info(f"V3 data: sqrtPriceX96={v3_data['sqrtPriceX96']}")
        return None

    flash_loan_amount = calculate_optimal_flash_loan(v2_price, v3_price)
    logger.info(f"Optimal flash loan amount: {flash_loan_amount} WETH")

    v3_fee = Decimal(v3_data['feeTier']) / Decimal('1000000')

    if v2_price < v3_price:
        # Buy on V2, sell on V3
        usdc_received = flash_loan_amount * v2_price
        weth_received = (usdc_received / v3_price) * (Decimal('1') - v3_fee)
        final_amount = weth_received
        direction = 'V2 to V3'
    else:
        # Buy on V3, sell on V2
        usdc_received = flash_loan_amount * v3_price * (Decimal('1') - v3_fee)
        weth_received = usdc_received / v2_price
        final_amount = weth_received
        direction = 'V3 to V2'

    profit = final_amount - flash_loan_amount
    profit_percentage = (profit / flash_loan_amount) * 100

    logger.info(f"Direction: {direction}")
    logger.info(f"Flash loan amount: {flash_loan_amount} WETH")
    logger.info(f"Final amount: {final_amount} WETH")
    logger.info(f"Profit: {profit} WETH")
    logger.info(f"Profit percentage: {profit_percentage}%")

    return {
        'direction': direction,
        'flash_loan_amount': flash_loan_amount,
        'final_amount': final_amount,
        'profit': profit,
        'profit_percentage': profit_percentage
    }

def main():
    while True:
        timestamp = datetime.now().isoformat()
        logger.info(f"Starting arbitrage calculation at {timestamp}")

        v2_data = query_uniswap_v2()
        v3_data = query_uniswap_v3()

        if v2_data and v3_data:
            logger.info(f"Raw V2 data: {v2_data}")
            logger.info(f"Raw V3 data: {v3_data}")

            arbitrage_result = calculate_arbitrage(v2_data, v3_data)
            if arbitrage_result:
                arbitrage_result['timestamp'] = timestamp
                print(json.dumps(arbitrage_result, indent=2, default=str))
        else:
            logger.error("Failed to fetch data from Uniswap contracts")

        logger.info("Waiting for 60 seconds before next calculation...")
        time.sleep(60)  # Wait 60 seconds between runs

if __name__ == "__main__":
    main()