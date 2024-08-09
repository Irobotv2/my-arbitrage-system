from web3 import Web3

# Connect to the Geth node
web3 = Web3(Web3.HTTPProvider('http://localhost:8545'))

# Check Sync Status
sync_status = web3.eth.syncing
print(f'Sync Status: {sync_status}')

# Get the Current Block Number
block_number = web3.eth.block_number
print(f'Current Block Number: {block_number}')
