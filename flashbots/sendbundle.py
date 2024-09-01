from flashbots import FlashbotsBundleProvider
from web3 import Web3
from eth_account import Account
from eth_account.signers.local import LocalAccount
import os

# Create a Web3 object
w3 = Web3(HTTPProvider("https://mainnet.infura.io/v3/0640f56f05a942d7a25cfeff50de344d"))

# Load your signing key
eth_account_signature: LocalAccount = Account.from_key(os.environ.get("ETH_SIGNATURE_KEY"))

# Set up the Flashbots provider
flashbots = FlashbotsBundleProvider(w3, eth_account_signature)

# Create your transaction (replace with your own logic)
transaction = {
    'to': '0xReceiverAddress',
    'value': w3.toWei(0.1, 'ether'),
    'gas': 21000,
    'gasPrice': w3.toWei('50', 'gwei'),
    'nonce': w3.eth.getTransactionCount(eth_account_signature.address),
    'chainId': 1
}

signed_tx = eth_account_signature.sign_transaction(transaction)

# Send the bundle (replace with your own logic)
block_number = w3.eth.block_number + 1
signed_bundle = flashbots.sign_bundle([signed_tx.rawTransaction])
result = flashbots.send_bundle(signed_bundle, block_number)

# Check the result
print(result)
