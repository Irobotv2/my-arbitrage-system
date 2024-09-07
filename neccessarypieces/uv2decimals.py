from web3 import Web3
import json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define constants for the Ethereum node
INFURA_URL = 'http://localhost:8545'  # Replace with your own Ethereum node URL

# Connect to the Ethereum node
w3 = Web3(Web3.HTTPProvider(INFURA_URL))

# Uniswap V2 Token and Pair Information
USDC_DECIMALS = 6  # USDC has 6 decimals
WETH_DECIMALS = 18  # WETH has 18 decimals

USDC_ADDRESS = w3.to_checksum_address('0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48')  # USDC contract address
WETH_ADDRESS = w3.to_checksum_address('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2')  # WETH contract address
UNISWAP_V2_PAIR_ABI = json.loads('[{"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"stateMutability":"view","type":"function"}]')

# Uniswap V2 Pair Address for USDC/WETH
PAIR_ADDRESS = w3.to_checksum_address('0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc')  # USDC/WETH pool

# Initialize the Uniswap V2 Pair contract
pair_contract = w3.eth.contract(address=PAIR_ADDRESS, abi=UNISWAP_V2_PAIR_ABI)

# Fetch reserves from the pair contract
def get_reserves():
    reserves = pair_contract.functions.getReserves().call()
    reserve_usdc = reserves[0] / (10 ** USDC_DECIMALS)  # Convert to human-readable format
    reserve_weth = reserves[1] / (10 ** WETH_DECIMALS)  # Convert to human-readable format
    logging.info(f"Reserves - USDC: {reserve_usdc}, WETH: {reserve_weth}")
    return reserve_usdc, reserve_weth

# Calculate the mid price
def calculate_mid_price():
    reserve_usdc, reserve_weth = get_reserves()
    mid_price = reserve_usdc / reserve_weth
    logging.info(f"Mid Price (USDC/WETH): {mid_price}")
    return mid_price

# Calculate the execution price for a trade
def calculate_execution_price(amount_in, token_in, token_out):
    reserve_usdc, reserve_weth = get_reserves()
    
    # Convert input amount to its smallest units
    if token_in == USDC_ADDRESS:
        amount_in = amount_in / (10 ** USDC_DECIMALS)  # Convert USDC to human-readable
    elif token_in == WETH_ADDRESS:
        amount_in = amount_in / (10 ** WETH_DECIMALS)  # Convert WETH to human-readable
    else:
        raise ValueError("Invalid token addresses")

    if token_in == USDC_ADDRESS and token_out == WETH_ADDRESS:
        amount_out = (amount_in * reserve_weth) / (reserve_usdc + amount_in)
    elif token_in == WETH_ADDRESS and token_out == USDC_ADDRESS:
        amount_out = (amount_in * reserve_usdc) / (reserve_weth + amount_in)
    else:
        raise ValueError("Invalid token addresses")

    # Convert output amount back to its smallest units
    if token_out == USDC_ADDRESS:
        amount_out = amount_out * (10 ** USDC_DECIMALS)  # Convert back to smallest unit
    elif token_out == WETH_ADDRESS:
        amount_out = amount_out * (10 ** WETH_DECIMALS)  # Convert back to smallest unit

    logging.info(f"Execution Price: {amount_in} {token_in} -> {amount_out} {token_out}")
    return amount_out

# Simulate a trade from USDC to WETH
def simulate_trade():
    amount_in_usdc = 1000 * (10 ** USDC_DECIMALS)  # Convert 1000 USDC to its smallest unit
    mid_price = calculate_mid_price()
    execution_price = calculate_execution_price(amount_in_usdc, USDC_ADDRESS, WETH_ADDRESS)
    logging.info(f"Simulated Trade: 1000 USDC -> {execution_price / (10 ** WETH_DECIMALS)} WETH")  # Convert back to human-readable format
    return execution_price

if __name__ == "__main__":
    simulate_trade()
