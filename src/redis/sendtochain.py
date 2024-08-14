import asyncio
import aiohttp
from decimal import Decimal
from web3 import Web3, AsyncWeb3
from web3.providers.async_rpc import AsyncHTTPProvider
import redis
import logging
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import networkx as nx

# Configure main logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='arbitrage_report.log', filemode='w')
logger = logging.getLogger()
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
logger.addHandler(console_handler)

# Configure path logging
path_logger = logging.getLogger('path_logger')
path_logger.setLevel(logging.INFO)
path_handler = logging.FileHandler('path_log.txt', mode='w')
path_handler.setFormatter(logging.Formatter('%(message)s'))
path_logger.addHandler(path_handler)

# Configure all paths logging
all_paths_logger = logging.getLogger('all_paths_logger')
all_paths_logger.setLevel(logging.INFO)
all_paths_handler = logging.FileHandler('all_analyzed_paths.log', mode='w')
all_paths_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
all_paths_logger.addHandler(all_paths_handler)

# Initialize Redis client
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Initialize Web3 with Tenderly provider
TENDERLY_URL = 'https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c'
w3 = AsyncWeb3(AsyncHTTPProvider(TENDERLY_URL))

YOUR_WALLET_ADDRESS = "0x19F5034FAB7e2CcA2Ad46EC28acF20cbd098D3fF"
YOUR_PRIVATE_KEY = "6d0ad7f50dccb88715e3592f39ea5be4c715531223b2daeb2de621dc8f6c230f"

# Contract setup
CONTRACT_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "tokenIn", "type": "address"},
                    {"internalType": "address", "name": "tokenOut", "type": "address"},
                    {"internalType": "address", "name": "pool", "type": "address"},
                    {"internalType": "bool", "name": "isV3", "type": "bool"},
                    {"internalType": "uint24", "name": "fee", "type": "uint24"},
                    {"internalType": "uint256", "name": "price", "type": "uint256"}
                ],
                "internalType": "struct FlashLoanArbitrage.SwapStep[]",
                "name": "path",
                "type": "tuple[]"
            },
            {"internalType": "uint256", "name": "flashLoanAmount", "type": "uint256"}
        ],
        "name": "executeArbitrage",
        "outputs": [
            {"internalType": "uint256", "name": "profit", "type": "uint256"}
        ],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

CONTRACT_ADDRESS = Web3.to_checksum_address("0x48334a214155101522519c5f6c2d82e46cb405d4")

# Price cache
price_cache = {}
CACHE_EXPIRY = 30  # seconds

async def get_pool_price(session, pool_address, is_v3):
    cache_key = f"{'v3' if is_v3 else 'v2'}_{pool_address}"
    if cache_key in price_cache and datetime.now() - price_cache[cache_key]['timestamp'] < timedelta(seconds=CACHE_EXPIRY):
        return price_cache[cache_key]['price']

    try:
        if is_v3:
            POOL_ABI = [{"inputs": [], "name": "slot0", "outputs": [{"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"}, {"internalType": "int24", "name": "tick", "type": "int24"}, {"internalType": "uint16", "name": "observationIndex", "type": "uint16"}, {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"}, {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"}, {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"}, {"internalType": "bool", "name": "unlocked", "type": "bool"}], "stateMutability": "view", "type": "function"}]
            contract = w3.eth.contract(address=pool_address, abi=POOL_ABI)
            slot0 = await contract.functions.slot0().call()
            sqrt_price_x96 = Decimal(slot0[0])
            price = (sqrt_price_x96 ** 2) / (2 ** 192)
            price = price * (10 ** 12)  # Adjust for decimals (USDT has 6, ETH has 18)
        else:
            PAIR_ABI = [{"constant": True, "inputs": [], "name": "getReserves", "outputs": [{"name": "reserve0", "type": "uint112"}, {"name": "reserve1", "type": "uint112"}, {"name": "blockTimestampLast", "type": "uint32"}], "type": "function"}]
            contract = w3.eth.contract(address=pool_address, abi=PAIR_ABI)
            reserves = await contract.functions.getReserves().call()
            reserve0, reserve1, _ = reserves
            if reserve0 == 0 or reserve1 == 0:
                raise Exception("One or both reserves are zero")
            price = (Decimal(reserve1) / Decimal(10**6)) / (Decimal(reserve0) / Decimal(10**18))

        price_cache[cache_key] = {'price': price, 'timestamp': datetime.now()}
        return price
    except Exception as e:
        logger.error(f"Error fetching price for pool {pool_address}: {e}")
        return None

def fetch_all_token_pairs():
    all_tokens = redis_client.keys("token:*")
    token_pairs = []
    for token1_key in all_tokens:
        token1_data = redis_client.hgetall(token1_key)
        for token2_key in all_tokens:
            if token1_key != token2_key:
                token2_data = redis_client.hgetall(token2_key)
                token_pairs.append((token1_data['address'], token2_data['address']))
    logger.info(f"Fetched {len(token_pairs)} token pairs from Redis")
    return token_pairs

async def find_multi_hop_arbitrage(session, start_token, flash_loan_amount, max_hops=3):
    paths = []
    paths_explored = 0
    async def dfs(current_token, path, amount, hop):
        nonlocal paths_explored
        paths_explored += 1
        if hop > max_hops:
            logger.debug(f"Max hops reached for path: {' -> '.join([get_token_symbol(t) for t, _, _ in path])}")
            return
        
        pools = get_pools_for_token(current_token)
        logger.debug(f"Found {len(pools)} pools for token {get_token_symbol(current_token)}")
        for pool in pools:
            next_token = get_other_token(pool, current_token)
            next_amount = await calculate_output_amount(session, pool, current_token, next_token, amount)
            new_path = path + [(current_token, next_token, pool)]
            
            # Log all analyzed paths
            log_analyzed_path(new_path, amount, next_amount)
            
            if next_token == start_token:
                if next_amount > flash_loan_amount:
                    profit = next_amount - flash_loan_amount
                    logger.info(f"Found profitable path: {' -> '.join([get_token_symbol(t) for t, _, _ in new_path])}")
                    logger.info(f"Estimated profit: {Web3.from_wei(profit, 'ether')} {get_token_symbol(start_token)}")
                    paths.append((new_path, profit))
                else:
                    logger.debug(f"Path complete but not profitable: {' -> '.join([get_token_symbol(t) for t, _, _ in new_path])}")
            else:
                await dfs(next_token, new_path, next_amount, hop + 1)
    
    await dfs(start_token, [], flash_loan_amount, 0)
    logger.info(f"Total paths explored: {paths_explored}")
    logger.info(f"Profitable paths found: {len(paths)}")
    return paths
def get_pools_for_token(token):
    v2_pools = redis_client.keys(f"uniswap_v2_pair:*:{token}:*")
    v3_pools = redis_client.keys(f"uniswap_v3_pool:*:{token}:*")
    return v2_pools + v3_pools

def get_other_token(pool, token):
    pool_data = redis_client.hgetall(pool)
    return pool_data['token1'] if pool_data['token0'] == token else pool_data['token0']

async def calculate_output_amount(session, pool, token_in, token_out, amount_in):
    pool_data = redis_client.hgetall(pool)
    is_v3 = 'v3_pool' in pool
    price = await get_pool_price(session, pool_data['pair_address'] if 'pair_address' in pool_data else pool_data['pool_address'], is_v3)
    if price is None:
        return 0
    output_amount = amount_in * price if token_in == pool_data['token0'] else amount_in / price
    
    # Log the swap details
    all_paths_logger.info(f"Swap: {Web3.from_wei(amount_in, 'ether')} {token_in} -> {Web3.from_wei(output_amount, 'ether')} {token_out}")
    all_paths_logger.info(f"Pool: {pool[:8]}... ({'V3' if is_v3 else 'V2'})")
    all_paths_logger.info(f"Price: {price}")
    
    return output_amount

def get_token_symbol(address):
    token_key = f"token:{address}"
    token_data = redis_client.hgetall(token_key)
    return token_data.get('symbol', address[:10])  # Return first 10 chars of address if symbol not found

def log_analyzed_path(path, initial_amount, final_amount):
    path_str = " -> ".join([f"{get_token_symbol(step[0])} ({step[2][:8]}...)" for step in path])
    profit = final_amount - initial_amount
    profit_percentage = (profit / initial_amount) * 100 if initial_amount != 0 else 0
    all_paths_logger.info(f"Path: {path_str}")
    all_paths_logger.info(f"Initial Amount: {Web3.from_wei(initial_amount, 'ether')} {get_token_symbol(path[0][0])}")
    all_paths_logger.info(f"Final Amount: {Web3.from_wei(final_amount, 'ether')} {get_token_symbol(path[-1][1])}")
    all_paths_logger.info(f"Profit: {Web3.from_wei(profit, 'ether')} {get_token_symbol(path[0][0])} ({profit_percentage:.2f}%)")
    all_paths_logger.info("------------------------")

def log_arbitrage_path(path, initial_amount):
    path_logger.info(f"Arbitrage Path:")
    path_logger.info(f"Initial Amount: {Web3.from_wei(initial_amount, 'ether')} {get_token_symbol(path[0][0])}")
    current_amount = initial_amount
    for i, (token_in, token_out, pool) in enumerate(path):
        pool_data = redis_client.hgetall(pool)
        pool_version = "V3" if 'v3_pool' in pool else "V2"
        output_amount = Web3.from_wei(current_amount, 'ether')
        path_logger.info(f"  Step {i+1}: {get_token_symbol(token_in)} -> {get_token_symbol(token_out)} ({pool_version})")
        path_logger.info(f"    Input: {output_amount:.6f} {get_token_symbol(token_in)}")
        path_logger.info(f"    Output: {output_amount:.6f} {get_token_symbol(token_out)}")
        current_amount = output_amount
    path_logger.info(f"  Final Amount: {current_amount:.6f} {get_token_symbol(path[-1][1])}")
    profit = current_amount - Web3.from_wei(initial_amount, 'ether')
    path_logger.info(f"  Profit: {profit:.6f} {get_token_symbol(path[0][0])}")
async def simulate_arbitrage(path, flash_loan_amount):
    logger.info(f"Simulating arbitrage for path: {' -> '.join([step[0] for step in path])}")
    contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)
    
    swap_steps = []
    for token_in, token_out, pool in path:
        pool_data = redis_client.hgetall(pool)
        is_v3 = 'v3_pool' in pool
        swap_steps.append({
            'tokenIn': Web3.to_checksum_address(token_in),
            'tokenOut': Web3.to_checksum_address(token_out),
            'pool': Web3.to_checksum_address(pool_data['pair_address'] if 'pair_address' in pool_data else pool_data['pool_address']),
            'isV3': is_v3,
            'fee': 3000 if is_v3 else 0,
            'price': Web3.to_wei('1', 'ether')  # This will be calculated dynamically in the contract
        })
    
    try:
        result = await contract.functions.executeArbitrage(swap_steps, flash_loan_amount).call({
            'from': YOUR_WALLET_ADDRESS,
        })
        
        profit = Web3.from_wei(result, 'ether')
        logger.info(f"Simulated profit: {profit} WETH")
        return {
            'success': True,
            'profit': profit,
            'path': swap_steps,
            'flash_loan_amount': flash_loan_amount
        }
    except Exception as e:
        logger.error(f"Simulation failed: {str(e)}")
        return {'success': False, 'error': str(e)}



async def main(run_time=5):
    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=run_time)
    
    flash_loan_amount = Web3.to_wei(1, 'ether')  # 1 WETH
    logger.info(f"Starting multi-hop arbitrage search. Will run until {end_time}")
    logger.info(f"Flash loan amount: {Web3.from_wei(flash_loan_amount, 'ether')} WETH")
    
    token_pairs = fetch_all_token_pairs()
    logger.info(f"Analyzing {len(token_pairs)} token pairs")
    
    all_opportunities = []
    simulated_opportunities = []
    executed_opportunities = []
    
    async with aiohttp.ClientSession() as session:
        while datetime.now() < end_time:
            for start_token, end_token in token_pairs:
                start_token_symbol = get_token_symbol(start_token)
                end_token_symbol = get_token_symbol(end_token)
                logger.info(f"Analyzing paths starting from: {start_token_symbol} to {end_token_symbol}")
                all_paths_logger.info(f"Starting analysis for token pair: {start_token_symbol} - {end_token_symbol}")
                all_paths_logger.info("============================")
                paths = await find_multi_hop_arbitrage(session, start_token, flash_loan_amount)
                
                for path, estimated_profit in paths:
                    log_arbitrage_path(path, flash_loan_amount)
                    simulation_result = await simulate_arbitrage(path, flash_loan_amount)
                    if simulation_result['success']:
                        all_opportunities.append({
                            'path': path,
                            'estimated_profit': estimated_profit,
                            'simulated_profit': simulation_result['profit']
                        })
                        simulated_opportunities.append(simulation_result)
                        
                        # Attempt to execute the arbitrage on Tenderly if profit is positive
                        if simulation_result['profit'] > 0:
                            success, tx_receipt = await execute_arbitrage_on_tenderly(path, flash_loan_amount)
                            if success:
                                logger.info(f"Successfully executed arbitrage on Tenderly. Profit: {simulation_result['profit']} WETH")
                                executed_opportunities.append({
                                    'path': path,
                                    'estimated_profit': estimated_profit,
                                    'simulated_profit': simulation_result['profit'],
                                    'tx_receipt': tx_receipt
                                })
                            else:
                                logger.warning(f"Failed to execute arbitrage on Tenderly. Simulated profit was: {simulation_result['profit']} WETH")
                
                all_paths_logger.info(f"Completed analysis for token pair: {start_token_symbol} - {end_token_symbol}")
                all_paths_logger.info("============================\n")
            
            logger.info(f"Completed iteration. Time elapsed: {datetime.now() - start_time}")
            await asyncio.sleep(1)  # Add a small delay to prevent overwhelming the system
    
    total_runtime = datetime.now() - start_time
    report = generate_detailed_report(all_opportunities, simulated_opportunities, executed_opportunities, total_runtime)
    logger.info("Multi-hop arbitrage search completed. Final report:")
    logger.info("\n" + report)

    return all_opportunities, simulated_opportunities, executed_opportunities, total_runtime

async def execute_arbitrage_on_tenderly(path, flash_loan_amount):
    logger.info(f"Executing arbitrage on Tenderly for path: {' -> '.join([get_token_symbol(step[0]) for step in path])}")
    contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)
    
    swap_steps = []
    for token_in, token_out, pool in path:
        pool_data = redis_client.hgetall(pool)
        is_v3 = 'v3_pool' in pool
        swap_steps.append({
            'tokenIn': Web3.to_checksum_address(token_in),
            'tokenOut': Web3.to_checksum_address(token_out),
            'pool': Web3.to_checksum_address(pool_data['pair_address'] if 'pair_address' in pool_data else pool_data['pool_address']),
            'isV3': is_v3,
            'fee': 3000 if is_v3 else 0,
            'price': Web3.to_wei('1', 'ether')  # This will be calculated dynamically in the contract
        })
    
    try:
        # Estimate gas
        gas_estimate = await contract.functions.executeArbitrage(
            flash_loan_amount,
            swap_steps
        ).estimate_gas({
            'from': YOUR_WALLET_ADDRESS,
        })
        logger.info(f"Estimated gas: {gas_estimate}")

        # Build transaction
        transaction = await contract.functions.executeArbitrage(
            flash_loan_amount,
            swap_steps
        ).build_transaction({
            'from': YOUR_WALLET_ADDRESS,
            'gas': int(gas_estimate * 1.2),  # Add 20% buffer
            'gasPrice': await w3.eth.gas_price,
            'nonce': await w3.eth.get_transaction_count(YOUR_WALLET_ADDRESS),
        })
        
        # Sign and send transaction
        signed_txn = w3.eth.account.sign_transaction(transaction, YOUR_PRIVATE_KEY)
        tx_hash = await w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        
        # Wait for transaction receipt
        tx_receipt = await w3.eth.wait_for_transaction_receipt(tx_hash)
        
        if tx_receipt['status'] == 1:
            logger.info(f"Arbitrage executed successfully on Tenderly. Transaction hash: {tx_receipt['transactionHash'].hex()}")
            logger.info(f"Gas used: {tx_receipt['gasUsed']}")
            return True, tx_receipt
        else:
            logger.error(f"Arbitrage execution failed on Tenderly. Transaction hash: {tx_receipt['transactionHash'].hex()}")
            return False, tx_receipt
    
    except Exception as e:
        logger.error(f"Error executing arbitrage on Tenderly: {str(e)}")
        return False, None

def generate_detailed_report(all_opportunities, simulated_opportunities, executed_opportunities, runtime):
    report = [
        f"1. Total runtime: {runtime}",
        f"2. Total potential opportunities found: {len(all_opportunities)}",
        f"3. Total simulated opportunities: {len(simulated_opportunities)}",
        f"4. Total executed opportunities: {len(executed_opportunities)}",
        "5. Detailed opportunity breakdown:"
    ]
    
    for idx, opp in enumerate(all_opportunities, 1):
        path = opp['path']
        report.extend([
            f"\nOpportunity {idx}:",
            f"   Path: {' -> '.join([get_token_symbol(step[0]) for step in path])}",
            f"   Estimated profit: {Web3.from_wei(opp['estimated_profit'], 'ether')} {get_token_symbol(path[0][0])}",
            f"   Simulated profit: {opp['simulated_profit']} {get_token_symbol(path[0][0])}",
            "   Execution path:"
        ])
        for i, (token_in, token_out, pool) in enumerate(path):
            pool_data = redis_client.hgetall(pool)
            pool_version = "V3" if 'v3_pool' in pool else "V2"
            report.append(f"     Step {i+1}: {get_token_symbol(token_in)} -> {get_token_symbol(token_out)} ({pool_version})")
    
    if executed_opportunities:
        report.append("\n6. Executed Opportunities:")
        for idx, opp in enumerate(executed_opportunities, 1):
            report.extend([
                f"\nExecuted Opportunity {idx}:",
                f"   Path: {' -> '.join([get_token_symbol(step[0]) for step in opp['path']])}",
                f"   Estimated profit: {Web3.from_wei(opp['estimated_profit'], 'ether')} {get_token_symbol(opp['path'][0][0])}",
                f"   Simulated profit: {opp['simulated_profit']} {get_token_symbol(opp['path'][0][0])}",
                f"   Transaction Hash: {opp['tx_receipt']['transactionHash'].hex()}",
                f"   Gas Used: {opp['tx_receipt']['gasUsed']}"
            ])
    
    return "\n".join(report)

async def run_arbitrage_bot():
    try:
        logger.info("Starting arbitrage bot...")
        result = await main(run_time=5)  # Run for 5 minutes
        logger.info("Main function completed. Processing results...")

        # Log the structure of the result
        logger.info(f"Result type: {type(result)}, Length: {len(result) if isinstance(result, (list, tuple)) else 'N/A'}")

        # Unpack the result carefully
        if isinstance(result, tuple) and len(result) == 4:
            opportunities, simulated_opportunities, executed_opportunities, total_runtime = result
        else:
            logger.error(f"Unexpected result structure from main(): {result}")
            return

        logger.info("Arbitrage bot run completed.")
        logger.info(f"Total runtime: {total_runtime}")
        logger.info(f"Total opportunities found: {len(opportunities)}")
        logger.info(f"Total simulated opportunities: {len(simulated_opportunities)}")
        logger.info(f"Total executed opportunities: {len(executed_opportunities)}")
        
        # Visualize the arbitrage paths
        if opportunities:
            visualize_arbitrage_paths(opportunities)
        
        # Generate and save a detailed report
        report = generate_detailed_report(opportunities, simulated_opportunities, executed_opportunities, total_runtime)
        with open('arbitrage_report.txt', 'w') as f:
            f.write(report)
        logger.info("Detailed report saved to 'arbitrage_report.txt'")
        
    except Exception as e:
        logger.error(f"Unexpected error in main execution: {str(e)}")
        logger.exception("Full traceback:")

logger.info("Arbitrage bot script execution completed.")
logger.info("Check 'all_analyzed_paths.log' for detailed path analysis.")

def visualize_arbitrage_paths(opportunities):
    G = nx.DiGraph()
    for opp in opportunities:
        path = opp['path']
        for i in range(len(path) - 1):
            G.add_edge(path[i][0][:6], path[i+1][0][:6], weight=opp['simulated_profit'])
    
    pos = nx.spring_layout(G)
    plt.figure(figsize=(12, 8))
    nx.draw(G, pos, with_labels=True, node_color='lightblue', node_size=3000, font_size=8, arrows=True)
    edge_labels = nx.get_edge_attributes(G, 'weight')
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels)
    plt.title("Multi-Hop Arbitrage Paths")
    plt.axis('off')
    plt.tight_layout()
    plt.savefig('arbitrage_paths.png', dpi=300, bbox_inches='tight')
    plt.close()
    logger.info("Arbitrage paths visualization saved as 'arbitrage_paths.png'")

if __name__ == "__main__":
    # Set up asyncio event loop
    loop = asyncio.get_event_loop()
    
    # Run the arbitrage bot
    loop.run_until_complete(run_arbitrage_bot())
    
    # Close the event loop
    loop.close()
    
    logger.info("Arbitrage bot script execution completed.")
    logger.info("Check 'all_analyzed_paths.log' for detailed path analysis.")