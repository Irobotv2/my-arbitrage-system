import os
from web3 import Web3
from solcx import compile_standard, install_solc
import json

# Install specific Solidity version
install_solc("0.7.0")

def deploy_contract():
    # Connect to Ganache
    w3 = Web3(Web3.HTTPProvider('http://localhost:8549'))

    # Set the default account (make sure this account is unlocked in Ganache)
    w3.eth.default_account = w3.eth.accounts[0]

    # Set the correct path to the Solidity file
    contract_path = "/home/irobot/projects/my-arbitrage-system/contracts/FlashloanBundleExecuter.sol"

    # Compile the contract
    with open(contract_path, "r") as file:
        contract_source_code = file.read()

    compiled_sol = compile_standard({
        "language": "Solidity",
        "sources": {
            "FlashloanBundleExecuter.sol": {
                "content": contract_source_code
            }
        },
        "settings": {
            "outputSelection": {
                "*": {
                    "*": ["abi", "metadata", "evm.bytecode", "evm.sourceMap"]
                }
            }
        }
    }, solc_version="0.7.0")

    # Get bytecode
    bytecode = compiled_sol['contracts']['FlashloanBundleExecuter.sol']['FlashLoanBundleExecutor']['evm']['bytecode']['object']

    # Get ABI
    abi = json.loads(compiled_sol['contracts']['FlashloanBundleExecuter.sol']['FlashLoanBundleExecutor']['metadata'])['output']['abi']

    # Create the contract in Python
    FlashLoanBundleExecutor = w3.eth.contract(abi=abi, bytecode=bytecode)

    # Get transaction count
    nonce = w3.eth.get_transaction_count(w3.eth.default_account)

    # Submit the transaction that deploys the contract
    tx_hash = FlashLoanBundleExecutor.constructor(w3.eth.default_account).transact({
        'from': w3.eth.default_account,
        'nonce': nonce,
    })

    # Wait for the transaction to be mined, and get the transaction receipt
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    print(f"Contract deployed to {tx_receipt.contractAddress}")

    # Optional: Test the contract
    contract_instance = w3.eth.contract(address=tx_receipt.contractAddress, abi=abi)
    print(f"Contract owner: {contract_instance.functions.owner().call()}")

    return tx_receipt.contractAddress

if __name__ == "__main__":
    contract_address = deploy_contract()
    print(f"Update your FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS with: {contract_address}")