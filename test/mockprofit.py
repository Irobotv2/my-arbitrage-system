import logging
from web3 import Web3
import time
from datetime import datetime

# Setup Web3 connection for executing transactions (Tenderly RPC)
provider_url_exec = 'https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c'
w3_exec = Web3(Web3.HTTPProvider(provider_url_exec))

# Define your wallet address and private key
wallet_address = "0x19F5034FAB7e2CcA2Ad46EC28acF20cbd098D3fF"
private_key = "6d0ad7f50dccb88715e3592f39ea5be4c715531223b2daeb2de621dc8f6c230f"  # Replace with your actual private key

# Contract addresses
UNISWAP_V2_ROUTER_ADDRESS = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
UNISWAP_V3_ROUTER_ADDRESS = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS = "0x26B7B5AB244114ab88578D5C4cD5b096097bf543"

# ABIs (You need to provide the full ABIs for these contracts)
V2_ROUTER_ABI = [
    {
        "name": "swapExactTokensForTokens",
        "type": "function",
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "amountOutMin", "type": "uint256"},
            {"name": "path", "type": "address[]"},
            {"name": "to", "type": "address"},
            {"name": "deadline", "type": "uint256"}
        ],
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]
V3_ROUTER_ABI = [
    {
        "name": "exactInputSingle",
        "type": "function",
        "inputs": [
            {
                "name": "params",
                "type": "tuple",
                "components": [
                    {"name": "tokenIn", "type": "address"},
                    {"name": "tokenOut", "type": "address"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "recipient", "type": "address"},
                    {"name": "deadline", "type": "uint256"},
                    {"name": "amountIn", "type": "uint256"},
                    {"name": "amountOutMinimum", "type": "uint256"},
                    {"name": "sqrtPriceLimitX96", "type": "uint160"}
                ]
            }
        ],
        "outputs": [{"name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function"
    }
]
FLASHLOAN_BUNDLE_EXECUTOR_ABI = [
    {
        "inputs": [
            {
                "internalType": "address",
                "name": "_executor",
                "type": "address"
            }
        ],
        "stateMutability": "nonpayable",
        "type": "constructor"
    },
    {
        "inputs": [],
        "name": "executor",
        "outputs": [
            {
                "internalType": "address",
                "name": "",
                "type": "address"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {
                "internalType": "contract IERC20[]",
                "name": "tokens",
                "type": "address[]"
            },
            {
                "internalType": "uint256[]",
                "name": "amounts",
                "type": "uint256[]"
            },
            {
                "internalType": "address[]",
                "name": "targets",
                "type": "address[]"
            },
            {
                "internalType": "bytes[]",
                "name": "payloads",
                "type": "bytes[]"
            }
        ],
        "name": "initiateFlashLoanAndBundle",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "owner",
        "outputs": [
            {
                "internalType": "address",
                "name": "",
                "type": "address"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {
                "internalType": "contract IERC20[]",
                "name": "tokens",
                "type": "address[]"
            },
            {
                "internalType": "uint256[]",
                "name": "amounts",
                "type": "uint256[]"
            },
            {
                "internalType": "uint256[]",
                "name": "feeAmounts",
                "type": "uint256[]"
            },
            {
                "internalType": "bytes",
                "name": "userData",
                "type": "bytes"
            }
        ],
        "name": "receiveFlashLoan",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

# Create contract instances
v2_router_contract = w3_exec.eth.contract(address=UNISWAP_V2_ROUTER_ADDRESS, abi=V2_ROUTER_ABI)
v3_router_contract = w3_exec.eth.contract(address=UNISWAP_V3_ROUTER_ADDRESS, abi=V3_ROUTER_ABI)
flashloan_contract = w3_exec.eth.contract(address=FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS, abi=FLASHLOAN_BUNDLE_EXECUTOR_ABI)

v3_pools = {
    '0.01%': '0xe6ff8b9A37B0fab776134636D9981Aa778c4e718',
    '0.05%': '0x4585FE77225b41b697C938B018E2Ac67Ac5a20c0',
    '0.30%': '0xCBCdF9626bC03E24f779434178A73a0B4bad62eD',
    '1.00%': '0x6Ab3bba2F41e7eAA262fa5A1A9b3932fA161526F'
}

# Global variables
REPORT_INTERVAL = 10  # Reduced for quicker testing
DETECTION_THRESHOLD = 0.01
EXECUTION_THRESHOLD = 0.015

opportunities = []

logging.basicConfig(level=logging.INFO)

def get_wbtc_weth_price_v2():
    # Implement actual price fetching from Uniswap V2
    return 22.0  # Mock price for now

def get_wbtc_weth_price_v3(pool_address):
    # Implement actual price fetching from Uniswap V3
    return 24.2  # Mock price for now

def determine_trade_direction(price_v2, price_v3):
    if price_v3 > price_v2 * (1 + EXECUTION_THRESHOLD):
        return "V2_TO_V3"
    elif price_v2 > price_v3 * (1 + EXECUTION_THRESHOLD):
        return "V3_TO_V2"
    else:
        return None

def execute_arbitrage(v3_pool_address, trade_direction, amount):
    logging.info(f"Executing arbitrage: {trade_direction}")
    logging.info(f"Flashloan amount: {amount / 10**18} ETH")
    
    if not w3_exec.is_connected():
        raise Exception("Not connected to Tenderly RPC")

    if trade_direction == "V2_TO_V3":
        targets = [UNISWAP_V2_ROUTER_ADDRESS, UNISWAP_V3_ROUTER_ADDRESS]
        logging.info(f"1. Borrowing WETH via flashloan from {FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS}")
        logging.info(f"2. Swapping WETH for WBTC on Uniswap V2 router {UNISWAP_V2_ROUTER_ADDRESS}")
        logging.info(f"3. Swapping WBTC for WETH on Uniswap V3 router {UNISWAP_V3_ROUTER_ADDRESS}")
        
        v2_swap_payload = v2_router_contract.encodeABI(
            fn_name="swapExactTokensForTokens",
            args=[
                amount, 
                0,
                ["0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"], 
                wallet_address, 
                int(time.time()) + 60 * 10
            ]
        )
        
        v3_swap_payload = v3_router_contract.encodeABI(
            fn_name="exactInputSingle",
            args=[{
                'tokenIn': "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
                'tokenOut': "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                'fee': 3000,
                'recipient': wallet_address,
                'deadline': int(time.time()) + 60 * 10,
                'amountIn': amount,
                'amountOutMinimum': 0,
                'sqrtPriceLimitX96': 0,
            }]
        )

        payloads = [v2_swap_payload, v3_swap_payload]

    else:
        targets = [UNISWAP_V3_ROUTER_ADDRESS, UNISWAP_V2_ROUTER_ADDRESS]
        logging.info(f"1. Borrowing WETH via flashloan from {FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS}")
        logging.info(f"2. Swapping WETH for WBTC on Uniswap V3 router {UNISWAP_V3_ROUTER_ADDRESS}")
        logging.info(f"3. Swapping WBTC for WETH on Uniswap V2 router {UNISWAP_V2_ROUTER_ADDRESS}")
        
        v3_swap_payload = v3_router_contract.encodeABI(
            fn_name="exactInputSingle",
            args=[{
                'tokenIn': "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                'tokenOut': "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
                'fee': 3000,
                'recipient': wallet_address,
                'deadline': int(time.time()) + 60 * 10,
                'amountIn': amount,
                'amountOutMinimum': 0,
                'sqrtPriceLimitX96': 0,
            }]
        )
        
        v2_swap_payload = v2_router_contract.encodeABI(
            fn_name="swapExactTokensForTokens",
            args=[
                amount, 
                0,
                ["0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"],
                wallet_address, 
                int(time.time()) + 60 * 10
            ]
        )

        payloads = [v3_swap_payload, v2_swap_payload]

    tokens = ["0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"]
    amounts = [amount, 0]  

    logging.info("4. Repaying flashloan + fees")

    try:
        # Get the latest nonce
        nonce = w3_exec.eth.get_transaction_count(wallet_address)
        logging.info(f"Nonce: {nonce}")

        # Get the current gas price
        gas_price = w3_exec.eth.gas_price
        logging.info(f"Gas Price: {gas_price}")

        # Build the transaction
        tx = flashloan_contract.functions.initiateFlashLoanAndBundle(
            tokens, amounts, targets, payloads
        ).build_transaction({
            'from': wallet_address,
            'nonce': nonce,
            'gas': 3000000,
            'gasPrice': gas_price,
        })

        # Sign the transaction
        signed_tx = w3_exec.eth.account.sign_transaction(tx, private_key=private_key)
        
        # Send the transaction
        tx_hash = w3_exec.eth.send_raw_transaction(signed_tx.rawTransaction)
        logging.info(f"Transaction sent to Tenderly. Hash: {tx_hash.hex()}")

        # Wait for the transaction receipt
        receipt = w3_exec.eth.wait_for_transaction_receipt(tx_hash)
        logging.info(f"Transaction mined. Status: {'Success' if receipt['status'] == 1 else 'Failed'}")
        logging.info(f"Transaction details: {receipt}")

    except Exception as e:
        logging.error(f"Error executing arbitrage: {str(e)}")
        logging.error(f"Error type: {type(e).__name__}")
        logging.error(f"Error details: {e.args}")

    logging.info("Arbitrage execution completed")


def monitor_arbitrage_opportunities():
    start_time = time.time()
    last_report_time = start_time

    while True:
        current_time = time.time()
        price_v2 = get_wbtc_weth_price_v2()

        for fee_tier, pool_address in v3_pools.items():
            price_v3 = get_wbtc_weth_price_v3(pool_address)

            logging.info(f"Uniswap V2 Price: {price_v2} WETH per WBTC")
            logging.info(f"Uniswap V3 ({fee_tier}) Price: {price_v3} WETH per WBTC")

            trade_direction = determine_trade_direction(price_v2, price_v3)
            
            if trade_direction:
                opportunity = {
                    "timestamp": current_time,
                    "type": trade_direction,
                    "fee_tier": fee_tier,
                    "price_v2": price_v2,
                    "price_v3": price_v3,
                    "profit_percentage": (max(price_v2, price_v3) / min(price_v2, price_v3) - 1) * 100
                }
                opportunities.append(opportunity)
                logging.info(f"Opportunity detected: {opportunity}")

                logging.info(f"Executing arbitrage: {trade_direction}")
                execute_arbitrage(pool_address, trade_direction, w3_exec.to_wei(1, 'ether'))

        if current_time - last_report_time >= REPORT_INTERVAL:
            generate_report(start_time, current_time)
            last_report_time = current_time
            opportunities.clear()

        time.sleep(0.1)  # Small delay to prevent overwhelming the system

def generate_report(start_time, end_time):
    report = f"Arbitrage Opportunity Report\n"
    report += f"Time period: {datetime.fromtimestamp(start_time)} to {datetime.fromtimestamp(end_time)}\n\n"

    if not opportunities:
        report += "No opportunities detected during this period.\n"
    else:
        report += f"Total opportunities detected: {len(opportunities)}\n"
        report += f"Opportunities exceeding execution threshold: {sum(1 for opp in opportunities if opp['profit_percentage'] >= EXECUTION_THRESHOLD * 100)}\n\n"

        report += "Top 10 opportunities:\n"
        top_opportunities = sorted(opportunities, key=lambda x: x['profit_percentage'], reverse=True)[:10]
        for i, opp in enumerate(top_opportunities, 1):
            report += f"{i}. {opp['type']} ({opp['fee_tier']})\n"
            report += f"   Timestamp: {datetime.fromtimestamp(opp['timestamp'])}\n"
            report += f"   V2 Price: {opp['price_v2']:.8f}\n"
            report += f"   V3 Price: {opp['price_v3']:.8f}\n"
            report += f"   Profit %: {opp['profit_percentage']:.2f}%\n\n"

    logging.info("Generating report...")
    logging.info(report)

    with open(f"arbitrage_report_{int(end_time)}.txt", "w") as f:
        f.write(report)

if __name__ == "__main__":
    logging.info("Starting arbitrage bot...")
    try:
        monitor_arbitrage_opportunities()
    except KeyboardInterrupt:
        logging.info("Arbitrage bot stopped by user.")
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
    finally:
        logging.info("Arbitrage bot shut down.")