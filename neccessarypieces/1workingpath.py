from web3 import Web3
import json
import logging

# Define constants for the Ethereum node
INFURA_URL = 'http://localhost:8545'  # Replace with your Ethereum node URL
QUOTER_CONTRACT_ADDRESS = '0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6'  # Uniswap V3 Quoter contract address on Ethereum mainnet

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

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Connect to the Ethereum node
w3 = Web3(Web3.HTTPProvider(INFURA_URL))

# Convert addresses to checksum format
USDC_ADDRESS = w3.to_checksum_address('0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48')
WETH_ADDRESS = w3.to_checksum_address('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2')
PAIR_ADDRESS = w3.to_checksum_address('0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc')

FEE_TIER = 500  # Fee tier for Uniswap V3 (0.05%)

# Initialize the Uniswap V3 Quoter contract
quoter_contract = w3.eth.contract(address=w3.to_checksum_address(QUOTER_CONTRACT_ADDRESS), abi=QUOTER_ABI)

# Uniswap V2 Pair ABI
UNISWAP_V2_PAIR_ABI = json.loads('[{"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"stateMutability":"view","type":"function"}]')

# Initialize the Uniswap V2 Pair contract
pair_contract = w3.eth.contract(address=PAIR_ADDRESS, abi=UNISWAP_V2_PAIR_ABI)

# Fetch reserves from the pair contract
def get_reserves():
    reserves = pair_contract.functions.getReserves().call()
    reserve_usdc = reserves[0] / (10 ** 6)  # Convert to human-readable format
    reserve_weth = reserves[1] / (10 ** 18)  # Convert to human-readable format
    logging.info(f"Reserves - USDC: {reserve_usdc}, WETH: {reserve_weth}")
    return reserve_usdc, reserve_weth

# Calculate the execution price for a trade on Uniswap V2
def calculate_execution_price(amount_in, token_in, token_out):
    reserve_usdc, reserve_weth = get_reserves()
    if token_in == USDC_ADDRESS:
        amount_in = amount_in / (10 ** 6)  # Convert USDC to human-readable
    elif token_in == WETH_ADDRESS:
        amount_in = amount_in / (10 ** 18)  # Convert WETH to human-readable
    else:
        raise ValueError("Invalid token addresses")

    if token_in == USDC_ADDRESS and token_out == WETH_ADDRESS:
        amount_out = (amount_in * reserve_weth) / (reserve_usdc + amount_in)
    elif token_in == WETH_ADDRESS and token_out == USDC_ADDRESS:
        amount_out = (amount_in * reserve_usdc) / (reserve_weth + amount_in)
    else:
        raise ValueError("Invalid token addresses")

    if token_out == USDC_ADDRESS:
        amount_out = amount_out * (10 ** 6)  # Convert back to smallest unit
    elif token_out == WETH_ADDRESS:
        amount_out = amount_out * (10 ** 18)  # Convert back to smallest unit

    logging.info(f"Execution Price: {amount_in} {token_in} -> {amount_out} {token_out}")
    return amount_out

# Get quote from Uniswap V3
def get_quote(amount_in_weth):
    try:
        amount_out_usdc = quoter_contract.functions.quoteExactInputSingle(
            WETH_ADDRESS,
            USDC_ADDRESS,
            FEE_TIER,
            int(amount_in_weth),  # WETH input amount
            0  # sqrtPriceLimitX96, set to 0 to not limit the price
        ).call()

        logging.info(f"Quote: {amount_in_weth / (10 ** 18)} WETH -> {amount_out_usdc / (10 ** 6):.6f} USDC")
        return amount_out_usdc

    except Exception as e:
        logging.error(f"Error fetching quote: {e}")
        return None

# Simulate arbitrage trade
def simulate_arbitrage():
    starting_usdc = 1000  # Starting amount of USDC
    logging.info(f"Starting USDC amount: {starting_usdc}")

    # Step 1: Swap USDC to WETH on Uniswap V2
    amount_in_usdc = starting_usdc * (10 ** 6)  # Convert to smallest unit
    amount_out_weth = calculate_execution_price(amount_in_usdc, USDC_ADDRESS, WETH_ADDRESS)

    # Step 2: Swap WETH back to USDC on Uniswap V3
    amount_out_usdc = get_quote(amount_out_weth)

    # Convert the amount back to human-readable format
    final_usdc = amount_out_usdc / (10 ** 6) if amount_out_usdc else 0

    # Log the final results
    logging.info(f"Ending USDC amount: {final_usdc:.6f}")
    profit = final_usdc - starting_usdc
    logging.info(f"Arbitrage Profit: {profit:.6f} USDC")

if __name__ == "__main__":
    simulate_arbitrage()
