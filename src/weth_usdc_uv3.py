from web3 import Web3
from web3.middleware import geth_poa_middleware
import pandas as pd
import numpy as np

# Configuration
TENDERLY_URL = "https://virtual.mainnet.rpc.tenderly.co/c4e60e60-6398-4e23-9ffc-f48f66d9706e"
web3 = Web3(Web3.HTTPProvider(TENDERLY_URL))
web3.middleware_onion.inject(geth_poa_middleware, layer=0)

# Uniswap V3 Factory and Quoter contract addresses (mainnet)
factory_address = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
quoter_address = "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6"

# ABIs
factory_abi = [
    {
        "inputs": [
            {"internalType": "address", "name": "token0", "type": "address"},
            {"internalType": "address", "name": "token1", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"}
        ],
        "name": "getPool",
        "outputs": [{"internalType": "address", "name": "pool", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]

quoter_abi = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenIn", "type": "address"},
            {"internalType": "address", "name": "tokenOut", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"}
        ],
        "name": "quoteExactInputSingle",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]

pool_abi = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
            {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
            {"internalType": "bool", "name": "unlocked", "type": "bool"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

liquidity_abi = [
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [
            {"internalType": "uint128", "name": "", "type": "uint128"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

# Create contract objects
factory_contract = web3.eth.contract(address=factory_address, abi=factory_abi)
quoter_contract = web3.eth.contract(address=quoter_address, abi=quoter_abi)

# Token addresses
usdc_address = web3.to_checksum_address("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606EB48")  # USDC mainnet address
weth_address = web3.to_checksum_address("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")  # WETH mainnet address

# Function to get pool address
def get_pool_address(tokenA, tokenB, fee):
    try:
        pool_address = factory_contract.functions.getPool(tokenA, tokenB, fee).call()
        return pool_address if pool_address != '0x0000000000000000000000000000000000000000' else None
    except Exception as e:
        print(f"Error getting pool address: {e}")
        return None

# Function to get pool liquidity
def get_pool_liquidity(pool_address):
    try:
        pool_contract = web3.eth.contract(address=pool_address, abi=liquidity_abi)
        liquidity = pool_contract.functions.liquidity().call()
        return liquidity
    except Exception as e:
        print(f"Error getting pool liquidity: {e}")
        return None

# Function to get a quote from the Quoter contract
def get_quote(tokenIn, tokenOut, amountIn, fee):
    try:
        amount_out = quoter_contract.functions.quoteExactInputSingle(
            tokenIn,
            tokenOut,
            fee,
            amountIn,
            0  # No price limit, set to 0 to not restrict the price
        ).call()
        return amount_out
    except Exception as e:
        print(f"Error getting quote: {e}")
        return None

# Check all fee tiers for a given pair and return the best quote
def get_best_quote(tokenA, tokenB, amountIn):
    fee_tiers = [500, 3000, 10000]  # 0.05%, 0.3%, 1% fee tiers
    best_quote = None
    best_fee = None
    for fee in fee_tiers:
        pool_address = get_pool_address(tokenA, tokenB, fee)
        if pool_address:
            pool_liquidity = get_pool_liquidity(pool_address)
            if pool_liquidity and pool_liquidity > 0:
                quote = get_quote(tokenA, tokenB, amountIn, fee)
                if quote:
                    if best_quote is None or quote > best_quote:
                        best_quote = quote
                        best_fee = fee
    return best_quote, best_fee



def get_weth_price_in_usd():
    # We'll use the WETH/USDC pool to get the WETH price in USD
    weth_amount = web3.to_wei(1, 'ether')  # 1 WETH
    best_quote, _ = get_best_quote(weth_address, usdc_address, weth_amount)
    if best_quote:
        return best_quote / 1e6  # Convert from USDC's 6 decimals to USD
    else:
        print("Failed to get WETH price in USD")
        return None

def calculate_weth_to_usdc(usd_amount):
    weth_price = get_weth_price_in_usd()
    if weth_price:
        weth_amount = (usd_amount / weth_price) * 1e18  # Convert to WETH's 18 decimals
        best_quote, best_fee = get_best_quote(weth_address, usdc_address, int(weth_amount))
        if best_quote:
            print(f"${usd_amount} worth of WETH ({weth_amount / 1e18:.6f} WETH) can be exchanged for {best_quote / 1e6:.2f} USDC")
            print(f"Best fee tier: {best_fee / 10000}%")
        else:
            print("Failed to get quote for WETH to USDC")
    else:
        print("Failed to calculate due to missing WETH price")

def test_liquidity_levels():
    weth_price = get_weth_price_in_usd()
    if not weth_price:
        print("Failed to get WETH price. Exiting.")
        return

    # Predefined liquidity levels
    liquidity_levels = [1000, 2000, 5000, 10000, 100000, 500000, 1000000, 10000000, 100000000, 1000000000]
    
    results = []
    for usd_amount in liquidity_levels:
        weth_amount = (usd_amount / weth_price) * 1e18  # Convert to WETH's 18 decimals
        best_quote, best_fee = get_best_quote(weth_address, usdc_address, int(weth_amount))
        if best_quote:
            usdc_received = best_quote / 1e6
            slippage = (usd_amount - usdc_received) / usd_amount * 100
            results.append({
                "USD Amount": usd_amount,
                "WETH Amount": weth_amount / 1e18,
                "USDC Received": usdc_received,
                "Best Fee Tier": best_fee / 10000,
                "Slippage %": slippage
            })
            
            # Print result immediately for each level
            print(f"\nLiquidity Test Result for ${usd_amount:.2f}:")
            print(f"WETH: {weth_amount / 1e18:.6f}")
            print(f"USDC Received: {usdc_received:.2f}")
            print(f"Best Fee Tier: {best_fee / 10000}%")
            print(f"Slippage: {slippage:.2f}%")
            print("----------------------")
        else:
            print(f"Failed to get quote for ${usd_amount:.2f}")

    # Find the liquidity level where slippage becomes significant
    significant_slippage = next((r for r in results if r['Slippage %'] > 1), None)
    if significant_slippage:
        print(f"\nSlippage becomes significant (>1%) at ${significant_slippage['USD Amount']:.2f}")
    else:
        print("\nSlippage did not become significant in the tested range")

# Run the liquidity test
test_liquidity_levels()