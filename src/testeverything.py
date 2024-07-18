from web3 import Web3
import json

# Initialize Web3 with Tenderly RPC
w3 = Web3(Web3.HTTPProvider("https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c"))

# Your deployed contract address
CONTRACT_ADDRESS = "0x781ef60721785a8307f40a2e6863f338a8844698"

# Load your contract ABI
with open('contract_abi.json', 'r') as abi_file:
    CONTRACT_ABI = json.load(abi_file)

# Initialize the contract
contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)

def execute_flash_loan_arbitrage(pair, amount, exchange):
    weth_price = get_weth_price_in_usd_v2() if exchange == 'v3' else get_weth_price_in_usd_v3()
    weth_amount = int((amount / weth_price) * 1e18)
    
    # Prepare parameters for initiateArbitrage
    tokens = [weth_address]
    amounts = [weth_amount]
    params = {
        'tokenIn': weth_address,
        'tokenOut': usdc_address,
        'amount': weth_amount,
        'minOutV2': int(weth_amount * 0.99),  # 1% slippage tolerance
        'minOutV3': int(weth_amount * 0.99),  # 1% slippage tolerance
        'v3Fee': 500 if exchange == 'v3' else 3000  # Adjust based on the best pool
    }

    # Estimate gas
    gas_estimate = contract.functions.initiateArbitrage(
        tokens, amounts, params
    ).estimate_gas({'from': ACCOUNT_ADDRESS})

    # Build the transaction
    transaction = contract.functions.initiateArbitrage(
        tokens, amounts, params
    ).build_transaction({
        'gas': int(gas_estimate * 1.2),  # Add 20% to gas estimate
        'gasPrice': w3.eth.gas_price,
        'nonce': w3.eth.get_transaction_count(ACCOUNT_ADDRESS),
    })

    # Sign and send the transaction
    signed_txn = w3.eth.account.sign_transaction(transaction, PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
    
    print(f"Flash loan arbitrage initiated. Transaction hash: {tx_hash.hex()}")
    return tx_hash

def check_arbitrage(pair, amount):
    exchange, diff = compare_exchanges(amount)
    if exchange and diff > 0:
        tx_hash = execute_flash_loan_arbitrage(pair, amount, exchange)
        # You might want to wait for the transaction to be mined and check the result
        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        print(f"Transaction mined in block {tx_receipt['blockNumber']}")
        # You could parse the transaction logs here to get more details about the arbitrage result
    else:
        print("No arbitrage opportunity found.")

# The rest of your code remains the same
import os
import requests
from web3 import Web3
from web3.middleware import geth_poa_middleware
from dotenv import load_dotenv
import time

# Load environment variables from .env file
load_dotenv()

# Configuration
TENDERLY_URL = "https://api.tenderly.co/api/v1/account/irobotv2noip/project/irobotv2/simulate"
TENDERLY_ACCESS_KEY = os.getenv("TENDERLY_ACCESS_KEY")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")  # Ensure your .env file contains PRIVATE_KEY
ACCOUNT_ADDRESS = os.getenv("ACCOUNT_ADDRESS")  # Ensure your .env file contains ACCOUNT_ADDRESS

web3 = Web3(Web3.HTTPProvider("https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c"))
web3.middleware_onion.inject(geth_poa_middleware, layer=0)

# Uniswap V2 Router address
uniswap_v2_router = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"

# Uniswap V3 Factory and Quoter contract addresses (mainnet)
factory_address = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
quoter_address = "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6"
uniswap_v3_router = "0xE592427A0AEce92De3Edee1F18E0157C05861564"

# ABIs
router_abi = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"}
        ],
        "name": "getAmountsOut",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForTokens",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

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

swap_abi_v3 = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenIn", "type": "address"},
            {"internalType": "address", "name": "tokenOut", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
            {"internalType": "address", "name": "recipient", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"},
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "amountOutMinimum", "type": "uint256"},
            {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"}
        ],
        "name": "exactInputSingle",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
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

erc20_abi = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [{"name": "_spender", "type": "address"}, {"name": "_value", "type": "uint256"}],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    }
]

# Create contract objects
router_contract = web3.eth.contract(address=uniswap_v2_router, abi=router_abi)
factory_contract = web3.eth.contract(address=factory_address, abi=factory_abi)
quoter_contract = web3.eth.contract(address=quoter_address, abi=quoter_abi)
router_contract_v3 = web3.eth.contract(address=uniswap_v3_router, abi=swap_abi_v3)

# Token addresses
usdc_address = web3.to_checksum_address("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606EB48")  # USDC mainnet address
weth_address = web3.to_checksum_address("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")  # WETH mainnet address

def get_token_balance(token_address, account_address):
    token_contract = web3.eth.contract(address=token_address, abi=erc20_abi)
    return token_contract.functions.balanceOf(account_address).call()

def print_balance_diff(token_address, balance_before, balance_after):
    diff = balance_after - balance_before
    print(f"Balance change for token {token_address}: {diff / 1e18} (before: {balance_before / 1e18}, after: {balance_after / 1e18})")

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

def get_weth_price_in_usd_v2():
    weth_amount = web3.to_wei(1, 'ether')  # 1 WETH
    try:
        amounts_out = router_contract.functions.getAmountsOut(
            weth_amount,
            [weth_address, usdc_address]
        ).call()
        return amounts_out[1] / 1e6  # Convert from USDC's 6 decimals to USD
    except Exception as e:
        print(f"Error getting WETH price: {e}")
        return None

def get_weth_price_in_usd_v3():
    weth_amount = web3.to_wei(1, 'ether')  # 1 WETH
    best_quote, _ = get_best_quote(weth_address, usdc_address, weth_amount)
    if best_quote:
        return best_quote / 1e6  # Convert from USDC's 6 decimals to USD
    else:
        print("Failed to get WETH price in USD")
        return None

def compare_exchanges(usd_amount):
    print(f"Comparing exchanges for ${usd_amount} WETH to USDC swap:")

    # Get V2 quote
    weth_price_v2 = get_weth_price_in_usd_v2()
    if weth_price_v2:
        weth_amount = (usd_amount / weth_price_v2) * 1e18
        amounts_out = router_contract.functions.getAmountsOut(
            int(weth_amount),
            [weth_address, usdc_address]
        ).call()
        usdc_out_v2 = amounts_out[1] / 1e6
        print(f"Uniswap V2: {usdc_out_v2:.2f} USDC")
    else:
        print("Failed to get Uniswap V2 quote")

    # Get V3 quote
    weth_price_v3 = get_weth_price_in_usd_v3()
    if weth_price_v3:
        weth_amount = (usd_amount / weth_price_v3) * 1e18
        best_quote, best_fee = get_best_quote(weth_address, usdc_address, int(weth_amount))
        if best_quote:
            usdc_out_v3 = best_quote / 1e6
            print(f"Uniswap V3: {usdc_out_v3:.2f} USDC (Fee tier: {best_fee/10000}%)")
        else:
            print("Failed to get Uniswap V3 quote")
    else:
        print("Failed to get Uniswap V3 WETH price")

    # Compare results
    if 'usdc_out_v2' in locals() and 'usdc_out_v3' in locals():
        diff = usdc_out_v3 - usdc_out_v2
        if diff > 0:
            print(f"Uniswap V3 offers better rate by {diff:.2f} USDC")
            return 'v3', diff  # Uniswap V3 is better
        elif diff < 0:
            print(f"Uniswap V2 offers better rate by {-diff:.2f} USDC")
            return 'v2', -diff  # Uniswap V2 is better
        else:
            print("Both exchanges offer the same rate")
            return None, 0

def approve_token(token_address, spender, amount):
    token_contract = web3.eth.contract(address=token_address, abi=erc20_abi)
    try:
        nonce = web3.eth.get_transaction_count(ACCOUNT_ADDRESS)
        tx = token_contract.functions.approve(spender, amount).build_transaction({
            'from': ACCOUNT_ADDRESS,
            'nonce': nonce,
            'gasPrice': web3.eth.gas_price,
            'gas': 200000
        })
        signed_tx = web3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.rawTransaction)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
        print(f"Approved {amount / 1e18} tokens for {spender}, transaction hash: {tx_hash.hex()}")
    except Exception as e:
        print(f"Error approving tokens: {str(e)}")

def execute_trade_v2(amount, path):
    amount = int(amount)  # Ensure amount is an integer
    path = list(path)  # Ensure path is a list
    try:
        # Check balance
        weth_contract = web3.eth.contract(address=weth_address, abi=erc20_abi)
        balance_before = weth_contract.functions.balanceOf(ACCOUNT_ADDRESS).call()

        if balance_before < amount:
            print(f"Insufficient WETH balance. Required: {amount / 1e18}, Available: {balance_before / 1e18}")
            return

        # Estimate gas
        gas_estimate = router_contract.functions.swapExactTokensForTokens(
            amount,
            0,  # amountOutMin: can set this to a reasonable value based on slippage tolerance
            path,
            ACCOUNT_ADDRESS,
            int(time.time()) + 60 * 10  # deadline
        ).estimate_gas({'from': ACCOUNT_ADDRESS})

        # Build the transaction
        transaction = router_contract.functions.swapExactTokensForTokens(
            amount,
            0,
            path,
            ACCOUNT_ADDRESS,
            int(time.time()) + 60 * 10
        ).build_transaction({
            'gas': gas_estimate,
            'from': ACCOUNT_ADDRESS,
            'nonce': web3.eth.get_transaction_count(ACCOUNT_ADDRESS),
            'gasPrice': web3.eth.gas_price
        })

        # Sign and send the transaction
        signed_txn = web3.eth.account.sign_transaction(transaction, private_key=PRIVATE_KEY)
        txn_hash = web3.eth.send_raw_transaction(signed_txn.rawTransaction)

        balance_after = weth_contract.functions.balanceOf(ACCOUNT_ADDRESS).call()
        print_balance_diff(weth_address, balance_before, balance_after)

        print(f"Uniswap V2 trade executed. Transaction hash: {txn_hash.hex()}")
    except Exception as e:
        print(f"Error executing Uniswap V2 trade: {str(e)}")

def execute_trade_v3(amount, tokenIn, tokenOut, fee):
    amount = int(amount)  # Ensure amount is an integer
    fee = int(fee)  # Ensure fee is an integer
    try:
        # Check balance
        token_contract = web3.eth.contract(address=tokenIn, abi=erc20_abi)
        balance_before = token_contract.functions.balanceOf(ACCOUNT_ADDRESS).call()

        if balance_before < amount:
            print(f"Insufficient balance. Required: {amount / 1e18}, Available: {balance_before / 1e18}")
            return

        # Estimate gas
        gas_estimate = router_contract_v3.functions.exactInputSingle(
            tokenIn,
            tokenOut,
            fee,
            ACCOUNT_ADDRESS,
            int(time.time()) + 60 * 10,  # deadline
            amount,
            0,  # amountOutMinimum: can set this to a reasonable value based on slippage tolerance
            0  # sqrtPriceLimitX96: set to 0 to not limit the price
        ).estimate_gas({'from': ACCOUNT_ADDRESS})

        # Build the transaction
        transaction = router_contract_v3.functions.exactInputSingle(
            tokenIn,
            tokenOut,
            fee,
            ACCOUNT_ADDRESS,
            int(time.time()) + 60 * 10,
            amount,
            0,
            0
        ).build_transaction({
            'gas': gas_estimate + 50000,  # Increase gas limit
            'from': ACCOUNT_ADDRESS,
            'nonce': web3.eth.get_transaction_count(ACCOUNT_ADDRESS),
            'gasPrice': web3.eth.gas_price
        })

        # Sign and send the transaction
        signed_txn = web3.eth.account.sign_transaction(transaction, private_key=PRIVATE_KEY)
        txn_hash = web3.eth.send_raw_transaction(signed_txn.rawTransaction)

        balance_after = token_contract.functions.balanceOf(ACCOUNT_ADDRESS).call()
        print_balance_diff(tokenIn, balance_before, balance_after)

        print(f"Uniswap V3 trade executed. Transaction hash: {txn_hash.hex()}")
    except Exception as e:
        print(f"Error executing Uniswap V3 trade: {str(e)}")

def check_arbitrage(pair, amount):
    exchange, diff = compare_exchanges(amount)
    if exchange and diff > 0:
        weth_price = get_weth_price_in_usd_v2() if exchange == 'v3' else get_weth_price_in_usd_v3()
        weth_amount = int((amount / weth_price) * 1e18)
        if exchange == 'v3':
            # Approve and execute buy on V2, sell on V3
            approve_token(weth_address, uniswap_v2_router, weth_amount)
            execute_trade_v2(weth_amount, [weth_address, usdc_address])
            approve_token(usdc_address, uniswap_v3_router, weth_amount)
            execute_trade_v3(weth_amount, weth_address, usdc_address, 500)  # Example fee tier
        elif exchange == 'v2':
            # Approve and execute buy on V3, sell on V2
            approve_token(weth_address, uniswap_v3_router, weth_amount)
            execute_trade_v3(weth_amount, weth_address, usdc_address, 500)  # Example fee tier
            approve_token(usdc_address, uniswap_v2_router, weth_amount)
            execute_trade_v2(weth_amount, [weth_address, usdc_address])
    else:
        print("No arbitrage opportunity found.")

# List of token pairs to monitor (contract addresses)
token_pairs = [
    (usdc_address, weth_address),
    # Add more pairs here
]

def get_token_info(address):
    # Implement this to get token symbol and decimals
    return {"symbol": "TOKEN", "decimals": 18}  # Placeholder implementation

def monitor_pairs():
    for pair in token_pairs:
        token0_info = get_token_info(pair[0])
        token1_info = get_token_info(pair[1])
        print(f"Checking {token0_info['symbol']}/{token1_info['symbol']} pair")
        
        # Check various amounts
        for amount in [1000, 10000, 100000]:
            check_arbitrage(pair, amount)
            time.sleep(1)  # Add delay to prevent rate limiting

# Run the monitoring
monitor_pairs()
