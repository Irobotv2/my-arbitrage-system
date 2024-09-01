from eth_account import Account

# Generate a new private key (only do this once and store it securely)
new_key = Account.create()

# Print the private key and public address
print(f"Private Key: {new_key._private_key.hex()}")  # Correct attribute is _private_key
print(f"Public Address: {new_key.address}")
