from eth_account import Account

# Replace with your actual private key
private_key = "6575ac283b8aa1cbd913d2d28557e318048f8e62a5a19a74001988e2f40ab06c"

# Load the account using the private key
account = Account.from_key(private_key)

# Print the public address to verify it matches your known wallet address
print(f"Public Address: {account.address}")

# Use this account as the signing key for Flashbots
eth_account_signature = account  # This will be used for Flashbots signing
