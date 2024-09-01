import time
import logging
import asyncio
import aiohttp
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account import Account
import redis
from datetime import datetime
import json
import threading
# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Web3 setup
PROVIDER_URL_LOCALHOST = 'http://localhost:8545'
PROVIDER_URL_EXEC = 'https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c'
w3_local = Web3(Web3.HTTPProvider(PROVIDER_URL_LOCALHOST, request_kwargs={'timeout': 30}))
w3_exec = Web3(Web3.HTTPProvider(PROVIDER_URL_EXEC))
w3_exec.middleware_onion.inject(geth_poa_middleware, layer=0)

# Wallet setup
WALLET_ADDRESS = "0x19F5034FAB7e2CcA2Ad46EC28acF20cbd098D3fF"
PRIVATE_KEY = "6d0ad7f50dccb88715e3592f39ea5be4c715531223b2daeb2de621dc8f6c230f"

# Contract addresses
UNISWAP_V2_WBTC_WETH_POOL = "0xBb2b8038a1640196FbE3e38816F3e67Cba72D940"
UNISWAP_V2_ROUTER_ADDRESS = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
UNISWAP_V3_ROUTER_ADDRESS = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS = "0x26B7B5AB244114ab88578D5C4cD5b096097bf543"

# V3 pools
v3_pools = {
    '0.01%': {'address': '0xe6ff8b9A37B0fab776134636D9981Aa778c4e718', 'fee': 100},
    '0.05%': {'address': '0x4585FE77225b41b697C938B018E2Ac67Ac5a20c0', 'fee': 500},
    '0.30%': {'address': '0xCBCdF9626bC03E24f779434178A73a0B4bad62eD', 'fee': 3000},
    '1.00%': {'address': '0x6Ab3bba2F41e7eAA262fa5A1A9b3932fA161526F', 'fee': 10000}
}

# ABIs (You need to provide the full ABIs for these contracts)
V2_POOL_ABI = [{"constant":True,"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"stateMutability":"view","type":"function"}]
V2_ROUTER_ABI = [{"name":"swapExactTokensForTokens","type":"function","inputs":[{"name":"amountIn","type":"uint256"},{"name":"amountOutMin","type":"uint256"},{"name":"path","type":"address[]"},{"name":"to","type":"address"},{"name":"deadline","type":"uint256"}],"outputs":[{"name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"}]
V3_POOL_ABI = [{"inputs":[],"name":"slot0","outputs":[{"internalType":"uint160","name":"sqrtPriceX96","type":"uint160"},{"internalType":"int24","name":"tick","type":"int24"},{"internalType":"uint16","name":"observationIndex","type":"uint16"},{"internalType":"uint16","name":"observationCardinality","type":"uint16"},{"internalType":"uint16","name":"observationCardinalityNext","type":"uint16"},{"internalType":"uint8","name":"feeProtocol","type":"uint8"},{"internalType":"bool","name":"unlocked","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"liquidity","outputs":[{"internalType":"uint128","name":"","type":"uint128"}],"stateMutability":"view","type":"function"}]
V3_ROUTER_ABI = [{"name":"exactInputSingle","type":"function","inputs":[{"name":"params","type":"tuple","components":[{"name":"tokenIn","type":"address"},{"name":"tokenOut","type":"address"},{"name":"fee","type":"uint24"},{"name":"recipient","type":"address"},{"name":"deadline","type":"uint256"},{"name":"amountIn","type":"uint256"},{"name":"amountOutMinimum","type":"uint256"},{"name":"sqrtPriceLimitX96","type":"uint160"}]}],"outputs":[{"name":"amountOut","type":"uint256"}],"stateMutability":"payable","type":"function"}]
FLASHLOAN_BUNDLE_EXECUTOR_ABI = [{"inputs":[{"internalType":"contract IERC20[]","name":"tokens","type":"address[]"},{"internalType":"uint256[]","name":"amounts","type":"uint256[]"},{"internalType":"address[]","name":"targets","type":"address[]"},{"internalType":"bytes[]","name":"payloads","type":"bytes[]"}],"name":"initiateFlashLoanAndBundle","outputs":[],"stateMutability":"nonpayable","type":"function"}]
ERC20_ABI = [{"constant":True,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"}]

# Create contract instances
v2_pool_contract = w3_local.eth.contract(address=UNISWAP_V2_WBTC_WETH_POOL, abi=V2_POOL_ABI)
v2_router_contract = w3_exec.eth.contract(address=UNISWAP_V2_ROUTER_ADDRESS, abi=V2_ROUTER_ABI)
v3_router_contract = w3_exec.eth.contract(address=UNISWAP_V3_ROUTER_ADDRESS, abi=V3_ROUTER_ABI)
flashloan_contract = w3_exec.eth.contract(address=FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS, abi=FLASHLOAN_BUNDLE_EXECUTOR_ABI)

# Redis setup
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Global variables
REPORT_INTERVAL = 2 * 60 * 60  # 2 hours in seconds
DETECTION_THRESHOLD = 0.005  # 0.5% threshold for detecting opportunities
EXECUTION_THRESHOLD = 0.01   # 1% threshold for executing arbitrage
opportunities = []

BUILDER_URLS = [
    "https://relay.flashbots.net",
    "https://builder0x69.io",
    "https://rpc.titanbuilder.xyz",
    "https://rpc.beaverbuild.org",
    "https://rsync-builder.xyz",
]

def get_token_decimals(token_address):
    token_contract = w3_local.eth.contract(address=token_address, abi=ERC20_ABI)
    return token_contract.functions.decimals().call()

def get_wbtc_weth_price_v2():
    reserves = v2_pool_contract.functions.getReserves().call()
    wbtc_reserve, weth_reserve = reserves[0], reserves[1]
    
    wbtc_decimals = get_token_decimals('0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599')
    weth_decimals = get_token_decimals('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2')

    normalized_wbtc_reserve = wbtc_reserve / (10 ** wbtc_decimals)
    normalized_weth_reserve = weth_reserve / (10 ** weth_decimals)

    return normalized_weth_reserve / normalized_wbtc_reserve

def sqrt_price_x96_to_price(sqrt_price_x96, token0_decimals, token1_decimals):
    price = (sqrt_price_x96 ** 2) / (2 ** 192)
    decimal_adjustment = 10 ** (token1_decimals - token0_decimals)
    return price * decimal_adjustment

def get_wbtc_weth_price_v3(pool_address):
    v3_pool_contract = w3_local.eth.contract(address=pool_address, abi=V3_POOL_ABI)
    slot0_data = v3_pool_contract.functions.slot0().call()
    sqrt_price_x96 = slot0_data[0]
    token0_decimals = get_token_decimals('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2')
    token1_decimals = get_token_decimals('0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599')
    return sqrt_price_x96_to_price(sqrt_price_x96, token0_decimals, token1_decimals)

def sort_tokens(token_a, token_b):
    return (token_a, token_b) if token_a.lower() < token_b.lower() else (token_b, token_a)

async def send_bundle_to_builder(session, url, bundle):
    try:
        async with session.post(url, json=bundle) as response:
            return await response.json()
    except Exception as e:
        logging.error(f"Error sending bundle to {url}: {str(e)}")
        return None

async def multiplex_builders(bundle):
    async with aiohttp.ClientSession() as session:
        tasks = [send_bundle_to_builder(session, url, bundle) for url in BUILDER_URLS]
        results = await asyncio.gather(*tasks)
    
    successful_submissions = [result for result in results if result is not None]
    return successful_submissions

def calculate_optimal_flashloan_amount(v3_pool_address, price_difference, gas_price):
    try:
        v3_pool_contract = w3_local.eth.contract(address=v3_pool_address, abi=V3_POOL_ABI)
        liquidity = v3_pool_contract.functions.liquidity().call()
        
        max_amount = liquidity / (10 ** 18)
        
        estimated_gas = 300000  # Adjust based on your transaction's typical gas usage
        gas_cost_in_eth = (gas_price * estimated_gas) / (10 ** 18)
        
        profit_per_unit = price_difference / 100
        optimal_amount = (gas_cost_in_eth / profit_per_unit) * 2  # Aim for 2x gas cost as minimum profit
        
        return min(optimal_amount, max_amount, w3_exec.to_wei(1000, 'ether'))
    except Exception as e:
        logging.error(f"Error calculating optimal flashloan amount: {str(e)}")
        return w3_exec.to_wei(1, 'ether')  # Return a default amount

def execute_arbitrage(v3_pool_info, is_v2_to_v3, max_amount):
    WETH_ADDRESS = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
    WBTC_ADDRESS = "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"
    
    sorted_tokens = sort_tokens(WETH_ADDRESS, WBTC_ADDRESS)

    flash_loan_amount = int(max_amount)

    logging.info(f"Preparing arbitrage: {'V2 to V3' if is_v2_to_v3 else 'V3 to V2'}")
    logging.info(f"Flash loan amount: {flash_loan_amount}")

    if is_v2_to_v3:
        targets = [UNISWAP_V2_ROUTER_ADDRESS, UNISWAP_V3_ROUTER_ADDRESS]
        
        v2_swap_payload = v2_router_contract.encodeABI(
            fn_name="swapExactTokensForTokens",
            args=[
                flash_loan_amount, 
                0, 
                sorted_tokens, 
                FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS,
                int(time.time()) + 60 * 10
            ]
        )
        
        v3_swap_payload = v3_router_contract.encodeABI(
            fn_name="exactInputSingle",
            args=[{
                'tokenIn': sorted_tokens[1],
                'tokenOut': sorted_tokens[0],
                'fee': v3_pool_info['fee'],
                'recipient': FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS,
                'deadline': int(time.time()) + 60 * 10,
                'amountIn': flash_loan_amount,
                'amountOutMinimum': 0,
                'sqrtPriceLimitX96': 0,
            }]
        )

        payloads = [v2_swap_payload, v3_swap_payload]

    else:
        targets = [UNISWAP_V3_ROUTER_ADDRESS, UNISWAP_V2_ROUTER_ADDRESS]
        
        v3_swap_payload = v3_router_contract.encodeABI(
            fn_name="exactInputSingle",
            args=[{
                'tokenIn': sorted_tokens[0],
                'tokenOut': sorted_tokens[1],
                'fee': v3_pool_info['fee'],
                'recipient': FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS,
                'deadline': int(time.time()) + 60 * 10,
                'amountIn': flash_loan_amount,
                'amountOutMinimum': 0,
                'sqrtPriceLimitX96': 0,
            }]
        )
        
        v2_swap_payload = v2_router_contract.encodeABI(
            fn_name="swapExactTokensForTokens",
            args=[
                flash_loan_amount, 
                0,
                list(reversed(sorted_tokens)),
                FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS,
                int(time.time()) + 60 * 10
            ]
        )

        payloads = [v3_swap_payload, v2_swap_payload]

    tokens = list(sorted_tokens)
    amounts = [flash_loan_amount, 0]

    try:
        nonce = w3_exec.eth.get_transaction_count(WALLET_ADDRESS)
        gas_price = w3_exec.eth.gas_price

        logging.info(f"Preparing transaction with nonce: {nonce}, gas price: {gas_price}")

        tx = flashloan_contract.functions.initiateFlashLoanAndBundle(
            tokens, amounts, targets, payloads
        ).build_transaction({
            'from': WALLET_ADDRESS,
            'nonce': nonce,
            'gas': 3000000,
            'gasPrice': gas_price,
        })

        signed_tx = w3_exec.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
        
        bundle = {
            "txs": [
                {
                    "signedTransaction": signed_tx.rawTransaction.hex(),
                    "signer": WALLET_ADDRESS,
                    "types": ["PEGGED_PRICE"],
                }
            ],
            "blockNumber": w3_exec.eth.block_number + 1,
            "minTimestamp": int(time.time()),
            "maxTimestamp": int(time.time()) + 120,
            "revertingTxHashes": []
        }

        logging.info(f"Submitting bundle to builders: {json.dumps(bundle, indent=2)}")

        loop = asyncio.get_event_loop()
        builder_results = loop.run_until_complete(multiplex_builders(bundle))

        logging.info(f"Bundle submitted to {len(builder_results)} builders successfully")
        for i, result in enumerate(builder_results, 1):
            logging.info(f"Builder {i} response: {json.dumps(result, indent=2)}")

        tx_hash = w3_exec.to_hex(w3_exec.keccak(signed_tx.rawTransaction))
        logging.info(f"Transaction hash: {tx_hash}")
        logging.info("Waiting for transaction receipt...")

        tx_receipt = w3_exec.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
        
        if tx_receipt['status'] == 1:
            logging.info("Transaction successful!")
            logging.info(f"Gas used: {tx_receipt['gasUsed']}")
            logging.info(f"Block number: {tx_receipt['blockNumber']}")
            
            # You might want to add logic here to check if the arbitrage was profitable
            # This would involve checking token balances before and after the transaction
            
        else:
            logging.error("Transaction failed!")
            logging.error(f"Transaction receipt: {json.dumps(dict(tx_receipt), indent=2)}")

    except Exception as e:
        logging.error(f"Error executing flashloan arbitrage: {str(e)}", exc_info=True)
        if 'tx_receipt' in locals():
            logging.error(f"Last known transaction receipt: {json.dumps(dict(tx_receipt), indent=2)}")

def monitor_arbitrage_opportunities():
    start_time = time.time()
    last_report_time = start_time

    while True:
        current_time = time.time()
        price_v2 = get_wbtc_weth_price_v2()

        for fee_tier, pool_info in v3_pools.items():
            price_v3 = get_wbtc_weth_price_v3(pool_info['address'])

            logging.info(f"Uniswap V2 Price: {price_v2} WETH per WBTC")
            logging.info(f"Uniswap V3 ({fee_tier}) Price: {price_v3} WETH per WBTC")

            if price_v3 > price_v2 * (1 + DETECTION_THRESHOLD):
                price_difference = (price_v3 / price_v2 - 1) * 100
                opportunity = {
                    "timestamp": current_time,
                    "type": "V2 to V3",
                    "fee_tier": fee_tier,
                    "price_v2": price_v2,
                    "price_v3": price_v3,
                    "profit_percentage": price_difference
                }
                opportunities.append(opportunity)
                logging.info(f"Opportunity detected: {opportunity}")

                if price_v3 > price_v2 * (1 + EXECUTION_THRESHOLD):
                    logging.info(f"Executing arbitrage: Uniswap V2 to Uniswap V3 ({fee_tier})")
                    gas_price = w3_exec.eth.gas_price
                    optimal_amount = calculate_optimal_flashloan_amount(pool_info['address'], price_difference, gas_price)
                    execute_arbitrage(pool_info, is_v2_to_v3=True, max_amount=optimal_amount)

            elif price_v2 > price_v3 * (1 + DETECTION_THRESHOLD):
                price_difference = (price_v2 / price_v3 - 1) * 100
                opportunity = {
                    "timestamp": current_time,
                    "type": "V3 to V2",
                    "fee_tier": fee_tier,
                    "price_v2": price_v2,
                    "price_v3": price_v3,
                    "profit_percentage": price_difference
                }
                opportunities.append(opportunity)
                logging.info(f"Opportunity detected: {opportunity}")

                if price_v2 > price_v3 * (1 + EXECUTION_THRESHOLD):
                    logging.info(f"Executing arbitrage: Uniswap V3 ({fee_tier}) to Uniswap V2")
                    gas_price = w3_exec.eth.gas_price
                    optimal_amount = calculate_optimal_flashloan_amount(pool_info['address'], price_difference, gas_price)
                    execute_arbitrage(pool_info, is_v2_to_v3=False, max_amount=optimal_amount)

        if current_time - last_report_time >= REPORT_INTERVAL:
            generate_report(start_time, current_time)
            last_report_time = current_time
            opportunities.clear()

        time.sleep(1)  # Adjust the sleep time as needed

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

def handle_event(event):
    logging.info(f"Received event: {event}")
    logging.info(f"Event type: {type(event)}")
    
    if isinstance(event, dict):
        for key, value in event.items():
            logging.info(f"Key: {key}, Value: {value}, Type: {type(value)}")
    
    if hasattr(event, 'transactionHash'):
        tx_hash = event.transactionHash
        if isinstance(tx_hash, bytes):
            tx_hash = tx_hash.hex()
        logging.info(f"New pending transaction: {tx_hash}")
        
        try:
            tx = w3_local.eth.get_transaction(tx_hash)
            logging.info(f"Transaction details: {tx}")
        except Exception as e:
            logging.error(f"Error getting transaction details: {str(e)}")
    else:
        logging.warning("Event doesn't contain a transactionHash attribute")

# Update the log_loop function to catch and log any exceptions
async def log_loop(event_filter, poll_interval):
    while True:
        try:
            for event in event_filter.get_new_entries():
                handle_event(event)
        except Exception as e:
            logging.error(f"Error in log_loop: {str(e)}", exc_info=True)
        await asyncio.sleep(poll_interval)

def run_block_watcher():
    def run_async_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        block_filter = w3_local.eth.filter('pending')
        try:
            loop.run_until_complete(log_loop(block_filter, 2))
        finally:
            loop.close()

    thread = threading.Thread(target=run_async_loop)
    thread.start()
    return thread

# In the main function, replace the existing block watcher code with:
if __name__ == "__main__":
    logging.info("Starting arbitrage bot and block watcher...")
    
    try:
        watcher_thread = run_block_watcher()
        
        monitor_arbitrage_opportunities()
    except KeyboardInterrupt:
        logging.info("Arbitrage bot stopped by user.")
    except Exception as e:
        logging.error(f"An error occurred in the main thread: {str(e)}", exc_info=True)
    finally:
        if 'watcher_thread' in locals():
            logging.info("Waiting for block watcher thread to terminate...")
            watcher_thread.join(timeout=5)
        logging.info("Arbitrage bot shut down.")