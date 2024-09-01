from flashbots import flashbot
from web3 import Web3
from eth_account.signers.local import LocalAccount
from eth_account.account import Account
import time

# Setup Web3 connections
TENDERLY_RPC_URL = 'https://virtual.sepolia.rpc.tenderly.co/7c0fd50a-138b-4520-8c0f-d2520ed59893'
INFURA_RPC_URL = 'https://sepolia.infura.io/v3/0640f56f05a942d7a25cfeff50de344d'

w3_tenderly = Web3(Web3.HTTPProvider(TENDERLY_RPC_URL))
w3_infura = Web3(Web3.HTTPProvider(INFURA_RPC_URL))

# Setup Flashbots
FLASHBOTS_RELAY_SEPOLIA = "https://relay-sepolia.flashbots.net"

# WARNING: Hardcoding private keys is extremely risky and should never be done in production code
SENDER_PRIVATE_KEY = "0x55ad53178afab1fe5c2bb7df434b88e115c3b0870235de7e6fd33623d8c749f3"
sender: LocalAccount = Account.from_key(SENDER_PRIVATE_KEY)

print(f"Using address: {sender.address}")
print("WARNING: This script contains a hardcoded private key. This is extremely unsafe and should only be used for testing on testnets.")

flashbot(w3_tenderly, sender, FLASHBOTS_RELAY_SEPOLIA)

def create_flashbots_bundle(signed_transaction):
    return [{"signed_transaction": signed_transaction}]

def get_nonce():
    # Get the nonce from Infura (actual Sepolia network)
    infura_nonce = w3_infura.eth.get_transaction_count(sender.address)
    tenderly_nonce = w3_tenderly.eth.get_transaction_count(sender.address, 'pending')
    print(f"Infura nonce: {infura_nonce}, Tenderly nonce: {tenderly_nonce}")
    return max(infura_nonce, tenderly_nonce)

def execute_flashbots_bundle():
    try:
        balance = w3_tenderly.eth.get_balance(sender.address)
        print(f"Tenderly simulated balance: {w3_tenderly.from_wei(balance, 'ether')} ETH")
        
        infura_balance = w3_infura.eth.get_balance(sender.address)
        print(f"Actual Sepolia balance (Infura): {w3_infura.from_wei(infura_balance, 'ether')} ETH")

        nonce = get_nonce()
        gas_price = w3_tenderly.eth.gas_price
        value = w3_tenderly.to_wei(0.0001, 'ether')
        gas = 21000

        total_cost = gas * gas_price + value
        if balance < total_cost:
            print(f"Error: Insufficient simulated funds. Have {w3_tenderly.from_wei(balance, 'ether')} ETH, need at least {w3_tenderly.from_wei(total_cost, 'ether')} ETH")
            return

        tx = {
            'nonce': nonce,
            'to': '0x742d35Cc6634C0532925a3b844Bc454e4438f44e',  # Example address
            'value': value,
            'gas': gas,
            'gasPrice': gas_price,
            'chainId': 11155111  # Sepolia chain ID
        }
        
        print(f"Transaction details:")
        print(f"  Nonce: {tx['nonce']}")
        print(f"  To: {tx['to']}")
        print(f"  Value: {w3_tenderly.from_wei(tx['value'], 'ether')} ETH")
        print(f"  Gas: {tx['gas']}")
        print(f"  Gas Price: {w3_tenderly.from_wei(tx['gasPrice'], 'gwei')} Gwei")
        print(f"  Total Cost: {w3_tenderly.from_wei(total_cost, 'ether')} ETH")

        signed_tx = sender.sign_transaction(tx)
        bundle = create_flashbots_bundle(signed_tx.rawTransaction)

        target_block_number = w3_tenderly.eth.block_number + 1
        
        simulation_result = w3_tenderly.flashbots.simulate(bundle, target_block_number)
        print(f"Simulation result: {simulation_result}")

        result = w3_tenderly.flashbots.send_bundle(bundle, target_block_number=target_block_number)
        
        print(f"Bundle submitted. Full result: {result}")
        
        bundle_hash = result.bundle_hash()
        if bundle_hash:
            hex_bundle_hash = w3_tenderly.to_hex(bundle_hash)
            print(f"Bundle hash: {hex_bundle_hash}")
            
            inclusion_result = result.wait(timeout=120)
            if inclusion_result:
                print(f"Bundle was included in block {inclusion_result}")
            else:
                print(f"Bundle not included. Current block: {w3_tenderly.eth.block_number}")
        else:
            print("Bundle submission failed. No bundle hash returned.")

    except Exception as e:
        print(f"Error: {str(e)}")
        print(f"Error type: {type(e)}")

if __name__ == "__main__":
    execute_flashbots_bundle()