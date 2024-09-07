from web3 import Web3
from web3.middleware import geth_poa_middleware
from web3.exceptions import ContractLogicError, BadFunctionCallOutput
import logging
import time
from decimal import Decimal
import json
import redis  # Import Redis library

# Initialize Web3
provider_url = 'https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c'
w3 = Web3(Web3.HTTPProvider(provider_url))
w3.middleware_onion.inject(geth_poa_middleware, layer=0)

# Ensure connection to the Ethereum node
if not w3.is_connected():
    print("Failed to connect to Ethereum node. Please check your connection and try again.")
    exit()

# Setup Logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Connect to Redis
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)  # Update host, port, db if necessary

# Wallet and contract details
wallet_address = Web3.to_checksum_address('0x19F5034FAB7e2CcA2Ad46EC28acF20cbd098D3fF')
private_key = '6d0ad7f50dccb88715e3592f39ea5be4c715531223b2daeb2de621dc8f6c230f'
contract_address = Web3.to_checksum_address('0x26B7B5AB244114ab88578D5C4cD5b096097bf543')



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

def calculate_optimal_flashloan_amount(token, pool_address):
    liquidity = Decimal(1000)  # Mock liquidity amount
    price_difference = Decimal(5)  # 5% arbitrage opportunity

    optimal_amount = max(min(liquidity * (price_difference / Decimal(100)), Decimal(100)), Decimal(1))
    logger.info(f"Calculated optimal flash loan amount: {optimal_amount} {token}")
    return optimal_amount

def convert_to_wei(amount, decimals=18):
    return int(Decimal(amount) * Decimal(10 ** decimals))

def build_transaction_payloads(token, pool_address, flash_loan_amount):
    logger.info("Building transaction payloads for the arbitrage...")

    # Convert the flash loan amount to Wei
    flash_loan_amount_wei = convert_to_wei(flash_loan_amount)

    payloads = [
        {
            "pool_address": pool_address,
            "flash_loan_amount": flash_loan_amount_wei,
            "token": token,
            "action": "swap"
        }
    ]
    
    logger.info("Constructed Payloads:")
    for payload in payloads:
        logger.info(f"  - Pool Address: {payload['pool_address']}")
        logger.info(f"  - Flash Loan Amount: {payload['flash_loan_amount']} {payload['token']} (in Wei)")
        logger.info(f"  - Action: {payload['action']}")
    
    return payloads

def execute_flashloan(transaction_payloads):
    logger.info("Executing arbitrage transaction...")
    for i, payload in enumerate(transaction_payloads, 1):
        logger.info(f"Executing payload {i}:")
        logger.info(f"  - Pool Address: {payload['pool_address']}")
        logger.info(f"  - Flash Loan Amount: {payload['flash_loan_amount']} {payload['token']}")
        logger.info(f"  - Action: {payload['action']}")

    # Build the transaction
    nonce = w3.eth.get_transaction_count(wallet_address)
    transaction = flashloan_executor.functions.initiateFlashLoanAndBundle(
        [tokens_and_pools[payload['token']]['address'] for payload in transaction_payloads],
        [payload['flash_loan_amount'] for payload in transaction_payloads],
        [wallet_address],
        ['0x']
    ).build_transaction({
        'from': wallet_address,
        'nonce': nonce,
        'gas': 3000000,
        'gasPrice': w3.to_wei('20', 'gwei')
    })

    # Sign the transaction
    signed_tx = w3.eth.account.sign_transaction(transaction, private_key=private_key)

    # Send the transaction
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    logger.info(f"Transaction sent: {tx_hash.hex()}")

    # Wait for the transaction receipt
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    logger.info(f"Transaction confirmed in block: {receipt.blockNumber}")
    logger.info(f"Gas used: {receipt.gasUsed}")

    if receipt.status == 1:
        logger.info("Flash loan executed successfully!")
    else:
        logger.info("Flash loan execution failed.")


def fetch_configurations_from_redis():
    # Fetch two configurations from Redis
    config1 = redis_client.get('USDC_wstETH_config')
    config2 = redis_client.get('USDT_WETH_config')
    
    if not config1 or not config2:
        logger.error("Failed to fetch configurations from Redis. Ensure that they are set.")
        return None, None
    
    return config1, config2

def process_configuration(config):
    selected_token, pool_address = select_token_for_flashloan(config)
    if pool_address:
        flash_loan_amount = calculate_optimal_flashloan_amount(selected_token, pool_address)
        transaction_payloads = build_transaction_payloads(selected_token, pool_address, flash_loan_amount)
        execute_flashloan(transaction_payloads)

# Main Function
def main():
    # Fetch configurations from Redis
    config1, config2 = fetch_configurations_from_redis()
    
    if not config1 or not config2:
        logger.error("No valid configurations found. Exiting.")
        return
    
    # Convert Redis data from JSON strings to dictionaries
    config1 = json.loads(config1)
    config2 = json.loads(config2)
    
    # Process both configurations
    logger.info("Processing first configuration...")
    process_configuration(config1)
    
    logger.info("Processing second configuration...")
    process_configuration(config2)

if __name__ == "__main__":
    main()