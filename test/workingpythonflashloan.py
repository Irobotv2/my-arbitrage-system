from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account import Account

# Initialize Web3
provider_url = 'https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c'  # HTTP URL
w3 = Web3(Web3.HTTPProvider(provider_url))

# Inject the Geth POA middleware (useful for certain Ethereum networks)
w3.middleware_onion.inject(geth_poa_middleware, layer=0)

# Your wallet address and private key
wallet_address = '0x19F5034FAB7e2CcA2Ad46EC28acF20cbd098D3fF'
private_key = '6d0ad7f50dccb88715e3592f39ea5be4c715531223b2daeb2de621dc8f6c230f'  # Replace with your actual private key

# FlashLoanBundleExecutor contract address
contract_address = '0x26B7B5AB244114ab88578D5C4cD5b096097bf543'

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
flashloan_executor = w3.eth.contract(address=contract_address, abi=FLASHLOAN_BUNDLE_EXECUTOR_ABI)

# Addresses
WETH_ADDRESS = '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'
AAVE_ADDRESS = '0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9'
aave_price_feed_address = '0x547a514d5e3769680Ce22B2361c10Ea13619e8a9'

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

# Price feed contract instance
price_feed_contract = w3.eth.contract(address=aave_price_feed_address, abi=price_feed_abi)

# Get AAVE price in USD
aave_price = price_feed_contract.functions.latestAnswer().call()
print(f"AAVE price (in cents): {aave_price}")

# Calculate AAVE amount for $100 million
one_hundred_million = 100_000_000 * 10**18
aave_amount = (one_hundred_million * 10**8) // aave_price

# Tokens and amounts
tokens = [WETH_ADDRESS, AAVE_ADDRESS]
amounts = [
    w3.to_wei(3700, 'ether'),  # 3700 WETH
    aave_amount  # $100 million worth of AAVE
]

# Sort tokens and amounts
sorted_pairs = sorted(zip(tokens, amounts), key=lambda x: x[0].lower())
tokens, amounts = zip(*sorted_pairs)

targets = [wallet_address]  # Example target
payloads = ["0x"]  # Empty payload

# Build the transaction
try:
    print("Initiating flash loan with parameters:")
    print("Tokens:", tokens)
    print("Amounts:", [str(a) for a in amounts])
    print("Targets:", targets)
    print("Payloads:", payloads)

    nonce = w3.eth.get_transaction_count(wallet_address)
    transaction = flashloan_executor.functions.initiateFlashLoanAndBundle(
        tokens,
        amounts,
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
    if hasattr(e, 'transaction'):
        print("Failed transaction details:", e.transaction)
    if hasattr(e, 'receipt'):
        print("Transaction receipt:", e.receipt)
