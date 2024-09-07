from web3 import Web3
import json

# Define constants
INFURA_URL = 'http://localhost:8545'
QUOTER_CONTRACT_ADDRESS = '0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6'  # Uniswap V3 Quoter contract address on Ethereum mainnet

# Uniswap V3 Quoter ABI
QUOTER_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenIn", "type": "address"},
            {"internalType": "address", "name": "tokenOut", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"},
        ],
        "name": "quoteExactInputSingle",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]

# Connect to the Ethereum node
w3 = Web3(Web3.HTTPProvider(INFURA_URL))

# Convert addresses to checksum format
USDC_ADDRESS = w3.to_checksum_address('0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48')  # USDC contract address
WETH_ADDRESS = w3.to_checksum_address('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2')  # WETH contract address
FEE_TIER = 500  # Fee tier for USDC/WETH pool (0.05%)

# Initialize the Quoter contract
quoter_contract = w3.eth.contract(address=w3.to_checksum_address(QUOTER_CONTRACT_ADDRESS), abi=QUOTER_ABI)

def get_quote(amount_in_usdc):
    # Convert input amount to the smallest unit (6 decimals for USDC)
    amount_in = int(amount_in_usdc * (10 ** 6))  # USDC has 6 decimals

    # Call the quoteExactInputSingle function
    try:
        amount_out = quoter_contract.functions.quoteExactInputSingle(
            USDC_ADDRESS,
            WETH_ADDRESS,
            FEE_TIER,
            amount_in,
            0  # sqrtPriceLimitX96, set to 0 to not limit the price
        ).call()

        # Convert the output amount from smallest unit (18 decimals for WETH)
        amount_out_weth = amount_out / (10 ** 18)  # WETH has 18 decimals

        print(f"Quote: {amount_in_usdc} USDC -> {amount_out_weth:.6f} WETH")
        return amount_out_weth

    except Exception as e:
        print(f"Error fetching quote: {e}")
        return None

if __name__ == "__main__":
    # Example usage: Get quote for 1000 USDC
    get_quote(1000)
