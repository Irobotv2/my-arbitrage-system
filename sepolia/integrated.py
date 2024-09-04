from flashbots import flashbot
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account.signers.local import LocalAccount
from eth_account.account import Account
import time

# Connect to Sepolia network using Infura
INFURA_RPC_URL = 'https://sepolia.infura.io/v3/0640f56f05a942d7a25cfeff50de344d'
w3 = Web3(Web3.HTTPProvider(INFURA_RPC_URL))
w3.middleware_onion.inject(geth_poa_middleware, layer=0)

# Setup Flashbots relay for Sepolia
FLASHBOTS_RELAY_SEPOLIA = "https://relay-sepolia.flashbots.net"

# Your private key and wallet address (Use with caution)
SENDER_PRIVATE_KEY = "6575ac283b8aa1cbd913d2d28557e318048f8e62a5a19a74001988e2f40ab06c"  # Replace with your actual private key
sender: LocalAccount = Account.from_key(SENDER_PRIVATE_KEY)

print(f"Using address: {sender.address}")
print("WARNING: This script contains a hardcoded private key. This is extremely unsafe and should only be used for testing on testnets.")

# Initialize Flashbots
flashbot(w3, sender, FLASHBOTS_RELAY_SEPOLIA)

# Sepolia-specific contract addresses
UNISWAP_V2_ROUTER_ADDRESS = Web3.to_checksum_address("0x815C1cEBED6a1a1aE71eA786AD7fC04f3057c769")
UNISWAP_V3_ROUTER_ADDRESS = Web3.to_checksum_address("0xE592427A0AEce92De3Edee1F18E0157C05861564")
FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS = Web3.to_checksum_address("0x67E5f53e4Fd6EdBdC7EBA56d868955ACf894F6eC")

# Define ABIs for contracts
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

# Initialize contract instances
flashloan_contract = w3.eth.contract(address=FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS, abi=FLASHLOAN_BUNDLE_EXECUTOR_ABI)
v2_router_contract = w3.eth.contract(address=UNISWAP_V2_ROUTER_ADDRESS, abi=V2_ROUTER_ABI)
v3_router_contract = w3.eth.contract(address=UNISWAP_V3_ROUTER_ADDRESS, abi=V3_ROUTER_ABI)

def create_flashbots_bundle(signed_transaction):
    return [{"signed_transaction": signed_transaction}]

def get_nonce():
    nonce = w3.eth.get_transaction_count(sender.address)
    print(f"Nonce: {nonce}")
    return nonce

def execute_flashloan_and_bundle():
    try:
        # Set up the flash loan parameters
        tokens = ["0xdd13E55209Fd76AfE204dBda4007C227904f0a81", "0x0FA8781a83E46826621b3BC094Ea2A0212e71B23"]  # Sepolia WETH and USDC addresses
        amounts = [1 * 10 ** 18, 1000 * 10 ** 6]  # 1 WETH and 1000 USDC
        targets = [UNISWAP_V2_ROUTER_ADDRESS, UNISWAP_V3_ROUTER_ADDRESS]  # Uniswap routers

        # Set realistic amountOutMin values to prevent slippage and front-running
        amount_out_min_v2 = int(amounts[0] * 0.99)  # Minimum 99% of input amount
        amount_out_min_v3 = int(amounts[1] * 0.99)  # Minimum 99% of input amount

        # Encode the payloads for the swaps
        v2_swap_payload = v2_router_contract.encodeABI(
            fn_name="swapExactTokensForTokens",
            args=[amounts[1], amount_out_min_v2, [tokens[1], tokens[0]], sender.address, int(time.time()) + 60]
        )
        v3_swap_payload = v3_router_contract.encodeABI(
            fn_name="exactInputSingle",
            args=[{
                'tokenIn': tokens[0], 'tokenOut': tokens[1], 'fee': 3000,
                'recipient': sender.address, 'deadline': int(time.time()) + 60,
                'amountIn': amounts[0], 'amountOutMinimum': amount_out_min_v3, 'sqrtPriceLimitX96': 0,
            }]
        )
        payloads = [v2_swap_payload, v3_swap_payload]

        # Build the transaction to call initiateFlashLoanAndBundle
        nonce = get_nonce()
        base_fee = w3.eth.get_block('latest')['baseFeePerGas']
        max_fee_per_gas = base_fee + Web3.to_wei(2, 'gwei')  # Setting max fee per gas a bit higher than base fee
        max_priority_fee_per_gas = Web3.to_wei(2, 'gwei')  # Setting priority fee

        tx = flashloan_contract.functions.initiateFlashLoanAndBundle(
            tokens, amounts, targets, payloads
        ).build_transaction({
            'from': sender.address,
            'nonce': nonce,
            'maxFeePerGas': max_fee_per_gas,
            'maxPriorityFeePerGas': max_priority_fee_per_gas,
            'gas': 500000,
            'chainId': 11155111  # Sepolia chain ID
        })

        # Sign the transaction
        signed_tx = sender.sign_transaction(tx)

        # Create a Flashbots bundle
        bundle = create_flashbots_bundle(signed_tx.rawTransaction)

        # Submit the bundle to the Flashbots relay
        target_block_number = w3.eth.block_number + 1
        simulation_result = w3.flashbots.simulate(bundle, target_block_number)
        print(f"Simulation result: {simulation_result}")

        if simulation_result.get('error'):
            print(f"Simulation error: {simulation_result['error']}")
            return

        result = w3.flashbots.send_bundle(bundle, target_block_number=target_block_number)
        print(f"Bundle submitted. Full result: {result}")

        bundle_hash = result.bundle_hash()
        if bundle_hash:
            hex_bundle_hash = w3.to_hex(bundle_hash)
            print(f"Bundle hash: {hex_bundle_hash}")

            # Wait for inclusion manually
            for _ in range(120):  # Wait for up to 120 seconds
                inclusion_result = result.receipts()
                if inclusion_result:
                    print(f"Bundle was included in block {inclusion_result}")
                    break
                else:
                    print(f"Waiting for inclusion... Current block: {w3.eth.block_number}")
                    time.sleep(1)
            else:
                print("Bundle not included after 120 seconds.")
        else:
            print("Bundle submission failed. No bundle hash returned.")

    except Exception as e:
        print(f"Error: {str(e)}")
        print(f"Error type: {type(e)}")

if __name__ == "__main__":
    execute_flashloan_and_bundle()
