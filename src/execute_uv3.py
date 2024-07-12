import os
import asyncio
from web3 import Web3, AsyncWeb3
from web3.middleware import geth_poa_middleware
from dotenv import load_dotenv
from functools import lru_cache

# Load environment variables from .env file
load_dotenv()

# Configuration
TENDERLY_URL = "https://api.tenderly.co/api/v1/account/irobotv2noip/project/irobotv2/simulate"
TENDERLY_ACCESS_KEY = os.getenv("TENDERLY_ACCESS_KEY")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
ACCOUNT_ADDRESS = os.getenv("ACCOUNT_ADDRESS")

web3 = Web3(Web3.HTTPProvider("https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c"))
web3.middleware_onion.inject(geth_poa_middleware, layer=0)
async_w3 = AsyncWeb3(Web3.AsyncHTTPProvider("https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c"))
async_w3.middleware_onion.inject(geth_poa_middleware, layer=0)

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
router_contract = async_w3.eth.contract(address=uniswap_v2_router, abi=router_abi)
factory_contract = async_w3.eth.contract(address=factory_address, abi=factory_abi)
quoter_contract = async_w3.eth.contract(address=quoter_address, abi=quoter_abi)
router_contract_v3 = async_w3.eth.contract(address=uniswap_v3_router, abi=swap_abi_v3)

# Token addresses
usdc_address = Web3.to_checksum_address("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606EB48")
weth_address = Web3.to_checksum_address("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")

@lru_cache(maxsize=100)
def get_token_info(address):
    return {"symbol": "TOKEN", "decimals": 18}  # Placeholder implementation

async def get_pool_address(tokenA, tokenB, fee):
    try:
        pool_address = await factory_contract.functions.getPool(tokenA, tokenB, fee).call()
        return pool_address if pool_address != '0x0000000000000000000000000000000000000000' else None
    except Exception as e:
        print(f"Error getting pool address: {e}")
        return None

async def get_token_balance(token_address, account_address):
    token_contract = async_w3.eth.contract(address=token_address, abi=erc20_abi)
    return await token_contract.functions.balanceOf(account_address).call()

def print_balance_diff(token_address, balance_before, balance_after):
    diff = balance_after - balance_before
    print(f"Balance change for token {token_address}: {diff / 1e18} (before: {balance_before / 1e18}, after: {balance_after / 1e18})")

async def get_wallet_balance():
    eth_balance = await async_w3.eth.get_balance(ACCOUNT_ADDRESS) / 1e18
    weth_balance = await get_token_balance(weth_address, ACCOUNT_ADDRESS) / 1e18
    usdc_balance = await get_token_balance(usdc_address, ACCOUNT_ADDRESS) / 1e6  # USDC has 6 decimals
    print(f"ETH Balance: {eth_balance:.6f} ETH")
    print(f"WETH Balance: {weth_balance:.6f} WETH")
    print(f"USDC Balance: {usdc_balance:.6f} USDC")
    return eth_balance, weth_balance, usdc_balance

async def log_balance(before=True):
    print("\nWallet balances {} trade:".format("before" if before else "after"))
    return await get_wallet_balance()

async def get_pool_liquidity(pool_address):
    try:
        pool_contract = async_w3.eth.contract(address=pool_address, abi=liquidity_abi)
        liquidity = await pool_contract.functions.liquidity().call()
        return liquidity
    except Exception as e:
        print(f"Error getting pool liquidity: {e}")
        return None

async def get_quote(tokenIn, tokenOut, amountIn, fee):
    try:
        amount_out = await quoter_contract.functions.quoteExactInputSingle(
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

async def get_best_quote(tokenA, tokenB, amountIn):
    fee_tiers = [500, 3000, 10000]  # 0.05%, 0.3%, 1% fee tiers
    best_quote = None
    best_fee = None
    for fee in fee_tiers:
        pool_address = await get_pool_address(tokenA, tokenB, fee)
        if pool_address:
            pool_liquidity = await get_pool_liquidity(pool_address)
            if pool_liquidity and pool_liquidity > 0:
                quote = await get_quote(tokenA, tokenB, amountIn, fee)
                if quote:
                    if best_quote is None or quote > best_quote:
                        best_quote = quote
                        best_fee = fee
    return best_quote, best_fee

async def get_weth_price_in_usd_v2():
    weth_amount = Web3.to_wei(1, 'ether')  # 1 WETH
    try:
        amounts_out = await router_contract.functions.getAmountsOut(
            weth_amount,
            [weth_address, usdc_address]
        ).call()
        return amounts_out[1] / 1e6  # Convert from USDC's 6 decimals to USD
    except Exception as e:
        print(f"Error getting WETH price: {e}")
        return None

async def get_weth_price_in_usd_v3():
    weth_amount = Web3.to_wei(1, 'ether')  # 1 WETH
    best_quote, _ = await get_best_quote(weth_address, usdc_address, weth_amount)
    if best_quote:
        return best_quote / 1e6  # Convert from USDC's 6 decimals to USD
    else:
        print("Failed to get WETH price in USD")
        return None

async def compare_exchanges(usd_amount):
    print(f"Comparing exchanges for ${usd_amount} WETH to USDC swap:")

    # Get V2 quote
    weth_price_v2 = await get_weth_price_in_usd_v2()
    if weth_price_v2:
        weth_amount = int((usd_amount / weth_price_v2) * 1e18)
        try:
            amounts_out = await router_contract.functions.getAmountsOut(
                weth_amount,
                [weth_address, usdc_address]
            ).call()
            usdc_out_v2 = amounts_out[1] / 1e6
            print(f"Uniswap V2: {usdc_out_v2:.2f} USDC")
        except Exception as e:
            print(f"Error getting Uniswap V2 quote: {e}")
            usdc_out_v2 = None
    else:
        print("Failed to get Uniswap V2 quote")
        usdc_out_v2 = None

    # Get V3 quote
    weth_price_v3 = await get_weth_price_in_usd_v3()
    if weth_price_v3:
        weth_amount = int((usd_amount / weth_price_v3) * 1e18)
        best_quote, best_fee = await get_best_quote(weth_address, usdc_address, weth_amount)
        if best_quote:
            usdc_out_v3 = best_quote / 1e6
            print(f"Uniswap V3: {usdc_out_v3:.2f} USDC (Fee tier: {best_fee/10000}%)")
        else:
            print("Failed to get Uniswap V3 quote")
            usdc_out_v3 = None
    else:
        print("Failed to get Uniswap V3 WETH price")
        usdc_out_v3 = None

    # Compare results
    if usdc_out_v2 is not None and usdc_out_v3 is not None:
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
    else:
        print("Unable to compare exchanges due to missing quotes")
        return None, 0

async def approve_token(token_address, spender, amount):
    token_contract = async_w3.eth.contract(address=token_address, abi=erc20_abi)
    try:
        nonce = await async_w3.eth.get_transaction_count(ACCOUNT_ADDRESS)
        tx = token_contract.functions.approve(spender, amount).build_transaction({
            'from': ACCOUNT_ADDRESS,
            'nonce': nonce,
            'gasPrice': await async_w3.eth.gas_price,
            'gas': 200000
        })
        signed_tx = await async_w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = await async_w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        receipt = await async_w3.eth.wait_for_transaction_receipt(tx_hash)
        print(f"Approved {amount / 1e18} tokens for {spender}, transaction hash: {tx_hash.hex()}")
    except Exception as e:
        print(f"Error approving tokens: {str(e)}")

async def execute_trade_v2(amount, path):
    await log_balance(before=True)
    amount = int(amount)  # Ensure amount is an integer
    path = list(path)  # Ensure path is a list
    try:
        # Check balance
        weth_contract = async_w3.eth.contract(address=weth_address, abi=erc20_abi)
        balance_before = await weth_contract.functions.balanceOf(ACCOUNT_ADDRESS).call()

        if balance_before < amount:
            print(f"Insufficient WETH balance. Required: {amount / 1e18}, Available: {balance_before / 1e18}")
            return

        # Estimate gas
        gas_estimate = await router_contract.functions.swapExactTokensForTokens(
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
            'nonce': await async_w3.eth.get_transaction_count(ACCOUNT_ADDRESS),
            'gasPrice': await async_w3.eth.gas_price
        })

        # Sign and send the transaction
        signed_txn = await async_w3.eth.account.sign_transaction(transaction, private_key=PRIVATE_KEY)
        txn_hash = await async_w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        await async_w3.eth.wait_for_transaction_receipt(txn_hash)

        balance_after = await weth_contract.functions.balanceOf(ACCOUNT_ADDRESS).call()
        print_balance_diff(weth_address, balance_before, balance_after)
        await log_balance(before=False)

        print(f"Uniswap V2 trade executed. Transaction hash: {txn_hash.hex()}")
    except Exception as e:
        print(f"Error executing Uniswap V2 trade: {str(e)}")
        if 'txn_hash' in locals():
            print(f"Revert reason: {await decode_revert_reason(txn_hash)}")

async def execute_trade_v3(amount, tokenIn, tokenOut, fee):
    amount = int(amount)  # Ensure amount is an integer
    fee = int(fee)  # Ensure fee is an integer
    try:
        print(f"Starting Uniswap V3 trade: {amount} of {tokenIn} to {tokenOut} with fee tier {fee}")
        
        # Check balance
        token_contract = async_w3.eth.contract(address=tokenIn, abi=erc20_abi)
        balance_before = await token_contract.functions.balanceOf(ACCOUNT_ADDRESS).call()
        print(f"Balance before trade: {balance_before / 1e18} {tokenIn}")

        if balance_before < amount:
            print(f"Insufficient balance. Required: {amount / 1e18}, Available: {balance_before / 1e18}")
            return

        # Estimate gas
        print("Estimating gas for the transaction...")
        try:
            gas_estimate = await router_contract_v3.functions.exactInputSingle(
                tokenIn,
                tokenOut,
                fee,
                ACCOUNT_ADDRESS,
                int(time.time()) + 60 * 10,  # deadline
                amount,
                0,  # amountOutMinimum: can set this to a reasonable value based on slippage tolerance
                0  # sqrtPriceLimitX96: set to 0 to not limit the price
            ).estimate_gas({'from': ACCOUNT_ADDRESS})
            print(f"Gas estimate: {gas_estimate}")
        except Exception as e:
            print(f"Gas estimation failed: {e}")
            print("Attempting to get more details about the failure...")
            try:
                await router_contract_v3.functions.exactInputSingle(
                    tokenIn,
                    tokenOut,
                    fee,
                    ACCOUNT_ADDRESS,
                    int(time.time()) + 60 * 10,
                    amount,
                    0,
                    0
                ).call({'from': ACCOUNT_ADDRESS})
            except Exception as call_exception:
                print(f"Detailed error: {call_exception}")
            return

        # Build the transaction
        print("Building the transaction...")
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
            'nonce': await async_w3.eth.get_transaction_count(ACCOUNT_ADDRESS),
            'gasPrice': await async_w3.eth.gas_price
        })
        print(f"Transaction built: {transaction}")

        # Sign and send the transaction
        print("Signing the transaction...")
        signed_txn = await async_w3.eth.account.sign_transaction(transaction, private_key=PRIVATE_KEY)
        print(f"Transaction signed: {signed_txn}")

        print("Sending the transaction...")
        txn_hash = await async_w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        print(f"Transaction sent. Hash: {txn_hash.hex()}")

        print("Waiting for transaction receipt...")
        receipt = await async_w3.eth.wait_for_transaction_receipt(txn_hash)
        print(f"Transaction receipt: {receipt}")

        balance_after = await token_contract.functions.balanceOf(ACCOUNT_ADDRESS).call()
        print_balance_diff(tokenIn, balance_before, balance_after)

        print(f"Uniswap V3 trade executed successfully. Transaction hash: {txn_hash.hex()}")
    except Exception as e:
        print(f"Error executing Uniswap V3 trade: {str(e)}")
        if 'txn_hash' in locals():
            revert_reason = await decode_revert_reason(txn_hash)
            print(f"Revert reason: {revert_reason}")

async def decode_revert_reason(tx_hash):
    print(f"Decoding revert reason for transaction hash: {tx_hash}")
    try:
        tx_receipt = await async_w3.eth.get_transaction_receipt(tx_hash)
        print(f"Transaction receipt: {tx_receipt}")
        
        tx = await async_w3.eth.get_transaction(tx_hash)
        print(f"Transaction details: {tx}")

        result = await async_w3.eth.call(tx, tx_receipt['blockNumber'] - 1)
    except Exception as e:
        print(f"Error decoding revert reason: {str(e)}")
        return str(e)

    revert_reason = Web3.to_text(result)
    print(f"Revert reason: {revert_reason}")
    return revert_reason

async def check_arbitrage(pair, amount):
    exchange, diff = await compare_exchanges(amount)
    if exchange and diff > 0:
        weth_price = await get_weth_price_in_usd_v2() if exchange == 'v3' else await get_weth_price_in_usd_v3()
        if weth_price:
            weth_amount = int((amount / weth_price) * 1e18)
            if exchange == 'v3':
                # Approve and execute buy on V2, sell on V3
                await approve_token(weth_address, uniswap_v2_router, weth_amount)
                await execute_trade_v2(weth_amount, [weth_address, usdc_address])
                await approve_token(usdc_address, uniswap_v3_router, weth_amount)
                await execute_trade_v3(weth_amount, weth_address, usdc_address, 500)  # Example fee tier
            elif exchange == 'v2':
                # Approve and execute buy on V3, sell on V2
                await approve_token(weth_address, uniswap_v3_router, weth_amount)
                await execute_trade_v3(weth_amount, weth_address, usdc_address, 500)  # Example fee tier
                await approve_token(usdc_address, uniswap_v2_router, weth_amount)
                await execute_trade_v2(weth_amount, [weth_address, usdc_address])
        else:
            print("Unable to get WETH price for arbitrage")
    else:
        print("No arbitrage opportunity found.")

# List of token pairs to monitor (contract addresses)
token_pairs = [
    (usdc_address, weth_address),
    # Add more pairs here
]

async def monitor_pairs_async():
    tasks = []
    for pair in token_pairs:
        for amount in [1000, 10000, 100000]:
            tasks.append(check_arbitrage(pair, amount))
    await asyncio.gather(*tasks)

# Run the monitoring
async def main():
    await monitor_pairs_async()

if __name__ == "__main__":
    asyncio.run(main())
