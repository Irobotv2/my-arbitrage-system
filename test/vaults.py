from web3 import Web3
from web3.middleware import geth_poa_middleware
from web3.exceptions import ContractLogicError, BadFunctionCallOutput
import time

# Initialize Web3
provider_url = 'https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c'
w3 = Web3(Web3.HTTPProvider(provider_url))
w3.middleware_onion.inject(geth_poa_middleware, layer=0)

# Ensure connection to the Ethereum node
if not w3.is_connected():
    print("Failed to connect to Ethereum node. Please check your connection and try again.")
    exit()

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
                    print(f"Failed to get price for {token} after {max_retries} attempts. Error: {str(e)}")
                    if token == 'wstETH':
                        print(f"Using fallback price for wstETH")
                        return 2500 * 10**8  # Assuming 1 wstETH ≈ 2500 USD
                    return None
                time.sleep(delay)
    elif token == 'sDAI':
        return 100000000  # Assuming 1 sDAI ≈ 1 USD
    elif token == 'osETH':
        weth_price = get_token_price('WETH')
        return int(weth_price * 1.05) if weth_price else None  # Assuming osETH is worth slightly more than ETH
    elif token == 'GYD':
        return 100000000  # Assuming 1 GYD ≈ 1 USD
    elif token == 'USDC':
        return 1000000  # Assuming 1 USDC ≈ 1 USD (Chainlink usually returns prices with 6 decimals for USDC)
    else:
        print(f"No price feed available for {token}")
        return None

# Define the amount to borrow for each token (100,000 USD)
hundred_thousand = 100_000 * 10**18  # Convert to wei (18 decimal places)

# Modify the main loop to use fewer tokens and smaller amounts
tokens = []
amounts = []
for token, info in list(tokens_and_pools.items())[:5]:  # Including USDC
    price = get_token_price(token)
    if price is not None and price > 0:
        amount = (hundred_thousand * 10**8) // price
        tokens.append(info['address'])
        amounts.append(amount)
    else:
        print(f"Skipping {token} due to unavailable or invalid price")

# Check if we have any valid tokens and amounts before proceeding
if not tokens or not amounts:
    print("No valid token prices found. Exiting.")
    exit()

# Sort tokens and amounts
sorted_pairs = sorted(zip(tokens, amounts), key=lambda x: x[0].lower())
tokens, amounts = zip(*sorted_pairs)

targets = [wallet_address]  # Example target
payloads = ["0x"]  # Single empty payload for all tokens

# Print the tokens and amounts for verification
print("Tokens to borrow:")
for token, amount in zip(tokens, amounts):
    print(f"Token: {token}, Amount: {amount}")

# Check wallet balance
balance = w3.eth.get_balance(wallet_address)
estimated_gas = 3000000  # This is an estimate, you might want to use eth_estimateGas for more accuracy
estimated_gas_price = w3.eth.gas_price
estimated_transaction_cost = estimated_gas * estimated_gas_price

if balance < estimated_transaction_cost:
    print(f"Warning: Insufficient funds in wallet. Balance: {w3.from_wei(balance, 'ether')} ETH")
    print(f"Estimated transaction cost: {w3.from_wei(estimated_transaction_cost, 'ether')} ETH")
    print("This transaction would fail on a real network due to insufficient funds.")
    print("Continuing simulation...")

# Rest of the code (try block) goes here...
try:
    print("Initiating flash loan with parameters:")
    print("Tokens:", tokens)
    print("Amounts:", [str(a) for a in amounts])
    print("Targets:", targets)
    print("Payloads:", payloads)

    nonce = w3.eth.get_transaction_count(wallet_address)
    transaction = flashloan_executor.functions.initiateFlashLoanAndBundle(
        list(tokens),
        list(amounts),
        targets,
        payloads
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
    print(f"Transaction sent: {tx_hash.hex()}")

    # Wait for the transaction receipt
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"Transaction confirmed in block: {receipt.blockNumber}")
    print(f"Gas used: {receipt.gasUsed}")

    if receipt.status == 1:
        print("Flash loan executed successfully!")
    else:
        print("Flash loan execution failed.")

except Exception as e:
    print(f"Error executing flash loan: {str(e)}")
    if "insufficient funds" in str(e):
        print("This error is expected when using a virtual RPC endpoint without actual funds.")
        print("In a real scenario, ensure your wallet has sufficient ETH for gas fees.")
    if hasattr(e, 'transaction'):
        print("Failed transaction details:", e.transaction)
    if hasattr(e, 'receipt'):
        print("Transaction receipt:", e.receipt)