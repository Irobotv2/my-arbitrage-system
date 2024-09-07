from web3 import Web3
from web3.middleware import geth_poa_middleware
from vaults import tokens_and_pools  # Import the tokens and pools dictionary
import logging
from decimal import Decimal

# Example configuration to test
config_to_test = {
    "name": "USDT-WETH",
    "v2_pool": "0x0d4a11d5EEaaC28EC3F61d100daF4d40471f1852",
    "v3_pools": {
        "1.00%": {"address": "0xc7bBeC68d12a0d1830360F8Ec58fA599bA1b0e9b", "fee": 100},
        "5.00%": {"address": "0x11b815efB8f581194ae79006d24E0d814B7697F6", "fee": 500},
        "30.00%": {"address": "0x4e68Ccd3E89f51C3074ca5072bbAC773960dFa36", "fee": 3000},
        "100.00%": {"address": "0xC5aF84701f98Fa483eCe78aF83F11b6C38ACA71D", "fee": 10000}
    },
    "token0": {"address": "0xdAC17F958D2ee523a2206206994597C13D831ec7", "symbol": "USDT"},
    "token1": {"address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "symbol": "WETH"}
}

# Setup Web3 Connection
provider_url = 'https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c'
w3 = Web3(Web3.HTTPProvider(provider_url))
w3.middleware_onion.inject(geth_poa_middleware, layer=0)

# Ensure Connection
if not w3.is_connected():
    print("Failed to connect to Ethereum node. Please check your connection and try again.")
    exit()

# Setup Logger with more readable format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Function to Detect Available Pool and Token for Arbitrage
def detect_pool_and_token_for_arbitrage(config):
    token0_symbol = config['token0']['symbol']
    token1_symbol = config['token1']['symbol']

    # Check if token0 or token1 has an available pool
    if token0_symbol in tokens_and_pools:
        pool_address = tokens_and_pools[token0_symbol]['pool']
        logger.info(f"Detected pool for {token0_symbol}: {pool_address}")
        return token0_symbol, pool_address
    elif token1_symbol in tokens_and_pools:
        pool_address = tokens_and_pools[token1_symbol]['pool']
        logger.info(f"Detected pool for {token1_symbol}: {pool_address}")
        return token1_symbol, pool_address
    else:
        logger.warning("No suitable Balancer pool detected for the tokens in this configuration.")
        return None, None

# Function to Calculate Optimal Flash Loan Amount
def calculate_optimal_flashloan_amount(token, pool_address):
    # Mock a liquidity check
    liquidity = Decimal(1000)  # Mock liquidity amount
    price_difference = Decimal(5)  # 5% arbitrage opportunity

    # Calculate the optimal flash loan amount
    optimal_amount = max(min(liquidity * (price_difference / Decimal(100)), Decimal(100)), Decimal(1))
    logger.info(f"Calculated optimal flash loan amount: {optimal_amount} {token}")
    return optimal_amount

# Function to Build Transaction Payloads
def build_transaction_payloads(token, pool_address, flash_loan_amount):
    logger.info("Building transaction payloads for the arbitrage...")

    payloads = [
        {
            "pool_address": pool_address,
            "flash_loan_amount": str(flash_loan_amount),
            "token": token,
            "action": "swap"
        }
    ]
    
    # Enhanced readability
    logger.info("Constructed Payloads:")
    for payload in payloads:
        logger.info(f"  - Pool Address: {payload['pool_address']}")
        logger.info(f"  - Flash Loan Amount: {payload['flash_loan_amount']} {payload['token']}")
        logger.info(f"  - Action: {payload['action']}")
    
    return payloads

# Function to Execute Arbitrage
def execute_arbitrage(transaction_payloads):
    logger.info("Simulating arbitrage transaction...")

    # Simulating execution
    for i, payload in enumerate(transaction_payloads, 1):
        logger.info(f"Simulating execution for payload {i}:")
        logger.info(f"  - Pool Address: {payload['pool_address']}")
        logger.info(f"  - Flash Loan Amount: {payload['flash_loan_amount']} {payload['token']}")
        logger.info(f"  - Action: {payload['action']}")

    logger.info("Arbitrage simulation completed.")

# Function to Select the Correct Token for Flash Loan
def select_token_for_flashloan(config, selected_token):
    """
    This function ensures that the flash loan is only requested for the specific token
    needed based on the arbitrage detection.
    """
    token_symbol, pool_address = detect_pool_and_token_for_arbitrage(config)

    if not pool_address or token_symbol != selected_token:
        logger.error("Selected token for flash loan is not matching detected arbitrage opportunity. Exiting.")
        return None, None

    flash_loan_amount = calculate_optimal_flashloan_amount(token_symbol, pool_address)

    # Only build payload for the selected token
    transaction_payloads = build_transaction_payloads(token_symbol, pool_address, flash_loan_amount)

    return transaction_payloads

# Main Function to Test the Configuration
def test_configuration(config):
    logger.info("Starting test for arbitrage configuration...")

    # Example: Select WETH for flash loan (modify dynamically based on your logic)
    selected_token = "WETH"

    # Call the function to select the correct token and get the payloads
    transaction_payloads = select_token_for_flashloan(config, selected_token)

    if not transaction_payloads:
        logger.error("No valid payloads generated for the flash loan. Exiting test.")
        return

    # Execute the arbitrage (simulation)
    execute_arbitrage(transaction_payloads)

    logger.info("Test completed. Review logs for detailed output.")
    return transaction_payloads

# Run the Test
if __name__ == "__main__":
    test_configuration(config_to_test)
