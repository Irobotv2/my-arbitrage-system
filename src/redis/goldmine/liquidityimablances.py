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
import sys
import traceback

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='arbitrage_bot.log', filemode='w')
logger = logging.getLogger()
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
logger.addHandler(console_handler)

# Initialize Redis client
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Initialize Web3 with Tenderly provider
TENDERLY_URL = 'https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c'
w3 = AsyncWeb3(AsyncHTTPProvider(TENDERLY_URL))

YOUR_WALLET_ADDRESS = "0x19F5034FAB7e2CcA2Ad46EC28acF20cbd098D3fF"
YOUR_PRIVATE_KEY = "6d0ad7f50dccb88715e3592f39ea5be4c715531223b2daeb2de621dc8f6c230f"

# Constants
PRICE_DEVIATION_THRESHOLD = 0.001  # 0.1%
LIQUIDITY_IMBALANCE_THRESHOLD = 0.05  # 5%
SCAN_INTERVAL = 30  # seconds
FLASH_LOAN_AMOUNT = Web3.to_wei(1, 'ether')  # 1 WETH

# Update the CONTRACT_ADDRESS
CONTRACT_ADDRESS = Web3.to_checksum_address("0x4F98A75f2C94D96f1f0d98D524171D4D0EB574d0")

# Update the CONTRACT_ABI
CONTRACT_ABI = [
    {
        "inputs": [],
        "stateMutability": "nonpayable",
        "type": "constructor"
    },
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
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
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
        "name": "simulateArbitrage",
        "outputs": [
            {"internalType": "uint256", "name": "estimatedProfit", "type": "uint256"},
            {"internalType": "uint256[]", "name": "simulationResults", "type": "uint256[]"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "token", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"}
        ],
        "name": "withdraw",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]
# Helper functions
def get_token_symbol(address):
    token_key = f"token:{address}"
    token_data = redis_client.hgetall(token_key)
    return token_data.get('symbol', address[:10])

async def get_pool_price(session, pool_address, is_v3):
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
        return price
    except Exception as e:
        logger.error(f"Error fetching price for pool {pool_address}: {e}")
        return None

async def scan_price_deviations():
    logger.info("Scanning for price deviations...")
    opportunities = []
    all_tokens = redis_client.keys("token:*")
    for token_key in all_tokens:
        token_data = redis_client.hgetall(token_key)
        token_address = token_data.get('address')
        token_symbol = token_data.get('symbol', 'Unknown')
        if not token_address:
            continue
        v2_pools = redis_client.keys(f"uniswap_v2_pair:*:{token_address}:*")
        v3_pools = redis_client.keys(f"uniswap_v3_pool:*:{token_address}:*")
        all_pools = v2_pools + v3_pools
        
        if len(all_pools) < 2:
            continue
        
        prices = []
        for pool_key in all_pools:
            pool_data = redis_client.hgetall(pool_key)
            is_v3 = 'v3_pool' in pool_key
            price = await get_pool_price(None, pool_data['pair_address'] if 'pair_address' in pool_data else pool_data['pool_address'], is_v3)
            if price:
                prices.append((price, pool_key))
        
        if len(prices) >= 2:
            max_price, max_pool = max(prices, key=lambda x: x[0])
            min_price, min_pool = min(prices, key=lambda x: x[0])
            deviation = (max_price - min_price) / min_price
            if deviation > PRICE_DEVIATION_THRESHOLD:
                opportunities.append({
                    'type': 'price_deviation',
                    'token': token_address,
                    'symbol': token_symbol,
                    'deviation': deviation,
                    'high_pool': max_pool,
                    'low_pool': min_pool,
                    'high_price': max_price,
                    'low_price': min_price
                })
    
    return opportunities

async def scan_liquidity_imbalances():
    logger.info("Scanning for liquidity imbalances...")
    opportunities = []
    v2_pools = redis_client.keys("uniswap_v2_pair:*")
    v3_pools = redis_client.keys("uniswap_v3_pool:*")
    all_pools = v2_pools + v3_pools
    
    for pool_key in all_pools:
        pool_data = redis_client.hgetall(pool_key)
        is_v3 = 'v3_pool' in pool_key
        if is_v3:
            liquidity = Decimal(pool_data['liquidity'])
            sqrt_price_x96 = Decimal(pool_data['sqrtPriceX96'])
            virtual_reserve0 = liquidity * (2**96) / sqrt_price_x96
            virtual_reserve1 = liquidity * sqrt_price_x96 / (2**96)
            if virtual_reserve1 == 0 or virtual_reserve0 == 0:
                continue
            imbalance = abs(virtual_reserve0 / virtual_reserve1 - 1)
        else:
            reserve0 = Decimal(pool_data['reserve0'])
            reserve1 = Decimal(pool_data['reserve1'])
            if reserve0 == 0 or reserve1 == 0:
                continue
            imbalance = abs(reserve0 / reserve1 - 1)
        
        if imbalance > LIQUIDITY_IMBALANCE_THRESHOLD:
            opportunities.append({
                'type': 'liquidity_imbalance',
                'pool': pool_key,
                'imbalance': imbalance,
                'token0': pool_data['token0'],
                'token1': pool_data['token1']
            })
    
    return opportunities

MAX_PRICE = Decimal('1e20')
MIN_PRICE = Decimal('1e-20')
MAX_PROFIT_PERCENTAGE = Decimal('10')

async def check_contract_balance(token_address):
    token_contract = w3.eth.contract(address=token_address, abi=[
        {
            "constant": True,
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "balance", "type": "uint256"}],
            "type": "function"
        }
    ])
    balance = await token_contract.functions.balanceOf(CONTRACT_ADDRESS).call()
    return balance

async def simulate_arbitrage(path, flash_loan_amount):
    logger.info(f"Simulating arbitrage for path: {' -> '.join([get_token_symbol(step[0]) for step in path])}")
    contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)
    
    swap_steps = []
    for token_in, token_out, pool in path:
        pool_data = redis_client.hgetall(pool)
        is_v3 = 'v3_pool' in pool
        price = await get_pool_price(None, pool_data['pair_address'] if 'pair_address' in pool_data else pool_data['pool_address'], is_v3)
        
        # Price sanity check
        if price is None or price < Decimal(MIN_PRICE) or price > Decimal(MAX_PRICE):
            logger.warning(f"Invalid price for {get_token_symbol(token_in)} -> {get_token_symbol(token_out)}: {price}")
            return {'success': False, 'error': 'Invalid price'}
        
        swap_step = {
            'tokenIn': Web3.to_checksum_address(token_in),
            'tokenOut': Web3.to_checksum_address(token_out),
            'pool': Web3.to_checksum_address(pool_data['pair_address'] if 'pair_address' in pool_data else pool_data['pool_address']),
            'isV3': is_v3,
            'fee': 3000 if is_v3 else 0,
            'price': Web3.to_wei(str(price), 'ether')
        }
        swap_steps.append(swap_step)
        logger.info(f"Swap step: {swap_step}")
    
    try:
        logger.info(f"Calling simulateArbitrage with flash loan amount: {flash_loan_amount}")
        result = await contract.functions.simulateArbitrage(swap_steps, flash_loan_amount).call({
            'from': YOUR_WALLET_ADDRESS,
        })
        
        estimated_profit, simulation_results = result
        profit = Decimal(Web3.from_wei(estimated_profit, 'ether'))
        
        # Profit sanity check
        flash_loan_amount_eth = Decimal(Web3.from_wei(flash_loan_amount, 'ether'))
        profit_percentage = (profit / flash_loan_amount_eth) * Decimal('100')
        if profit_percentage > Decimal(MAX_PROFIT_PERCENTAGE):
            logger.warning(f"Unusually high profit percentage: {profit_percentage}%")
            return {'success': False, 'error': 'Unusually high profit'}
        
        logger.info(f"Simulated profit: {profit} WETH ({profit_percentage:.2f}%)")
        return {
            'success': True,
            'profit': profit,
            'path': swap_steps,
            'flash_loan_amount': flash_loan_amount,
            'simulation_results': simulation_results,
            'profit_percentage': profit_percentage
        }
    except Exception as e:
        logger.error(f"Exception in simulate_arbitrage: {str(e)}")
        logger.error(f"Exception type: {type(e)}")
        logger.error(f"Exception args: {e.args}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {'success': False, 'error': str(e), 'traceback': traceback.format_exc()}
async def execute_arbitrage_on_tenderly(path, flash_loan_amount):
    logger.info(f"Executing arbitrage on Tenderly for path: {' -> '.join([get_token_symbol(step[0]) for step in path])}")
    contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)
    
    try:
        # Check contract balance
        initial_balance = await check_contract_balance(path[0][0])
        logger.info(f"Initial contract balance: {Web3.from_wei(initial_balance, 'ether')} WETH")

        # Prepare swap steps
        swap_steps = []
        for token_in, token_out, pool in path:
            pool_data = redis_client.hgetall(pool)
            is_v3 = 'v3_pool' in pool
            price = await get_pool_price(None, pool_data['pair_address'] if 'pair_address' in pool_data else pool_data['pool_address'], is_v3)
            
            swap_step = {
                'tokenIn': Web3.to_checksum_address(token_in),
                'tokenOut': Web3.to_checksum_address(token_out),
                'pool': Web3.to_checksum_address(pool_data['pair_address'] if 'pair_address' in pool_data else pool_data['pool_address']),
                'isV3': is_v3,
                'fee': 3000 if is_v3 else 0,
                'price': Web3.to_wei(str(price), 'ether')
            }
            swap_steps.append(swap_step)
            logger.info(f"Prepared swap step: {swap_step}")

        # Estimate gas
        try:
            gas_estimate = await contract.functions.executeArbitrage(swap_steps, flash_loan_amount).estimate_gas({
                'from': YOUR_WALLET_ADDRESS,
            })
            logger.info(f"Estimated gas: {gas_estimate}")
        except Exception as e:
            logger.error(f"Gas estimation failed: {str(e)}")
            return False, None, None

        # Get current gas price
        gas_price = await w3.eth.gas_price
        logger.info(f"Current gas price: {gas_price}")

        # Calculate total gas cost
        gas_cost = gas_estimate * gas_price
        logger.info(f"Estimated gas cost: {Web3.from_wei(gas_cost, 'ether')} ETH")

        # Build transaction
        try:
            transaction = await contract.functions.executeArbitrage(swap_steps, flash_loan_amount).build_transaction({
                'from': YOUR_WALLET_ADDRESS,
                'gas': int(gas_estimate * 1.2),  # Add 20% buffer
                'gasPrice': gas_price,
                'nonce': await w3.eth.get_transaction_count(YOUR_WALLET_ADDRESS),
            })
            logger.info(f"Transaction built successfully: {transaction}")
        except Exception as e:
            logger.error(f"Transaction build failed: {str(e)}")
            return False, None, None

        # Sign and send transaction
        try:
            signed_txn = w3.eth.account.sign_transaction(transaction, YOUR_PRIVATE_KEY)
            tx_hash = await w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            logger.info(f"Transaction sent. Hash: {tx_hash.hex()}")
        except Exception as e:
            logger.error(f"Transaction signing or sending failed: {str(e)}")
            return False, None, None

        # Wait for transaction receipt
        try:
            tx_receipt = await w3.eth.wait_for_transaction_receipt(tx_hash)
            logger.info(f"Transaction receipt received: {tx_receipt}")
        except Exception as e:
            logger.error(f"Waiting for transaction receipt failed: {str(e)}")
            return False, None, None

        if tx_receipt['status'] == 1:
            logger.info(f"Arbitrage executed successfully. Gas used: {tx_receipt['gasUsed']}")
            
            # Check final balance
            final_balance = await check_contract_balance(path[0][0])
            profit = final_balance - initial_balance
            logger.info(f"Final balance: {Web3.from_wei(final_balance, 'ether')} WETH")
            logger.info(f"Actual profit: {Web3.from_wei(profit, 'ether')} WETH")
            
            return True, tx_receipt, profit
        else:
            logger.error(f"Arbitrage execution failed. Transaction reverted.")
            return False, tx_receipt, None

    except Exception as e:
        logger.error(f"Unexpected error in execute_arbitrage_on_tenderly: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False, None, None
async def handle_opportunity(opportunity, opportunity_type):
    if opportunity_type == 'price_deviation':
        path = [
            (opportunity['token'], opportunity['token'], opportunity['low_pool']),
            (opportunity['token'], opportunity['token'], opportunity['high_pool'])
        ]
    else:  # liquidity_imbalance
        path = [
            (opportunity['token0'], opportunity['token1'], opportunity['pool']),
            (opportunity['token1'], opportunity['token0'], opportunity['pool'])
        ]
    
    simulation_result = await simulate_arbitrage(path, FLASH_LOAN_AMOUNT)
    
    if simulation_result['success'] and simulation_result['profit'] > 0:
        success, tx_receipt, actual_profit = await execute_arbitrage_on_tenderly(path, FLASH_LOAN_AMOUNT)
        if success:
            logger.info(f"Successfully executed {opportunity_type} arbitrage. Simulated Profit: {simulation_result['profit']} WETH, Actual Profit: {Web3.from_wei(actual_profit, 'ether')} WETH")
            return True, simulation_result['profit'], actual_profit, tx_receipt, simulation_result
        else:
            logger.warning(f"Failed to execute {opportunity_type} arbitrage on Tenderly.")
            return False, 0, 0, tx_receipt, simulation_result
    else:
        logger.info(f"Simulation unsuccessful or unprofitable for {opportunity_type} opportunity.")
        return False, 0, 0, None, simulation_result

async def handle_price_deviation(opportunity):
    # Construct the arbitrage path
    path = [
        (opportunity['token'], opportunity['token'], opportunity['low_pool']),
        (opportunity['token'], opportunity['token'], opportunity['high_pool'])
    ]
    
    # Simulate the arbitrage
    simulation_result = await simulate_arbitrage(path, FLASH_LOAN_AMOUNT)
    
    if simulation_result['success'] and simulation_result['profit'] > 0:
        # Execute the arbitrage
        success, tx_receipt = await execute_arbitrage_on_tenderly(path, FLASH_LOAN_AMOUNT)
        if success:
            logger.info(f"Successfully executed price deviation arbitrage. Profit: {simulation_result['profit']} WETH")
            return True, simulation_result['profit'], tx_receipt
    
    return False, 0, None

async def handle_liquidity_imbalance(opportunity):
    # Construct the arbitrage path
    path = [
        (opportunity['token0'], opportunity['token1'], opportunity['pool']),
        (opportunity['token1'], opportunity['token0'], opportunity['pool'])
    ]
    
    # Simulate the arbitrage
    simulation_result = await simulate_arbitrage(path, FLASH_LOAN_AMOUNT)
    
    if simulation_result['success'] and simulation_result['profit'] > 0:
        # Execute the arbitrage
        success, tx_receipt = await execute_arbitrage_on_tenderly(path, FLASH_LOAN_AMOUNT)
        if success:
            logger.info(f"Successfully executed liquidity imbalance arbitrage. Profit: {simulation_result['profit']} WETH")
            return True, simulation_result['profit'], tx_receipt
    
    return False, 0, None

async def main_loop(all_opportunities, executed_opportunities):
    try:
        # Scan for price deviations
        price_opportunities = await scan_price_deviations()
        logger.info(f"Found {len(price_opportunities)} price deviation opportunities")
        for idx, opp in enumerate(price_opportunities, 1):
            logger.info(f"Processing price deviation opportunity {idx}/{len(price_opportunities)}")
            logger.info(f"Opportunity details: Token: {get_token_symbol(opp['token'])}, Deviation: {opp['deviation']:.4f}")
            success, simulated_profit, actual_profit, receipt, simulation_result = await handle_opportunity(opp, 'price_deviation')
            all_opportunities.append({**opp, 'success': success, 'simulated_profit': simulated_profit, 'actual_profit': actual_profit, 'receipt': receipt, 'simulation_result': simulation_result})
            if success:
                executed_opportunities.append({**opp, 'simulated_profit': simulated_profit, 'actual_profit': actual_profit, 'receipt': receipt, 'simulation_result': simulation_result})
        
        # Scan for liquidity imbalances
        imbalance_opportunities = await scan_liquidity_imbalances()
        logger.info(f"Found {len(imbalance_opportunities)} liquidity imbalance opportunities")
        for idx, opp in enumerate(imbalance_opportunities, 1):
            logger.info(f"Processing liquidity imbalance opportunity {idx}/{len(imbalance_opportunities)}")
            logger.info(f"Opportunity details: Pool: {opp['pool']}, Imbalance: {opp['imbalance']:.4f}")
            success, simulated_profit, actual_profit, receipt, simulation_result = await handle_opportunity(opp, 'liquidity_imbalance')
            all_opportunities.append({**opp, 'success': success, 'simulated_profit': simulated_profit, 'actual_profit': actual_profit, 'receipt': receipt, 'simulation_result': simulation_result})
            if success:
                executed_opportunities.append({**opp, 'simulated_profit': simulated_profit, 'actual_profit': actual_profit, 'receipt': receipt, 'simulation_result': simulation_result})
        
    except Exception as e:
        logger.error(f"Error in main loop: {str(e)}")
        logger.exception("Full traceback:")
    
    # Add a delay to prevent overwhelming the system
    await asyncio.sleep(SCAN_INTERVAL)

def visualize_arbitrage_paths(opportunities):
    G = nx.DiGraph()
    for opp in opportunities:
        if 'path' in opp:
            path = opp['path']
            for i in range(len(path) - 1):
                G.add_edge(get_token_symbol(path[i][0])[:6], get_token_symbol(path[i+1][0])[:6], weight=opp.get('profit', 0))
    
    if not G.nodes():
        logger.info("No paths to visualize")
        return
    
    pos = nx.spring_layout(G)
    plt.figure(figsize=(12, 8))
    nx.draw(G, pos, with_labels=True, node_color='lightblue', node_size=3000, font_size=8, arrows=True)
    edge_labels = nx.get_edge_attributes(G, 'weight')
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels)
    plt.title("Arbitrage Paths")
    plt.axis('off')
    plt.tight_layout()
    plt.savefig('arbitrage_paths.png', dpi=300, bbox_inches='tight')
    plt.close()
    logger.info("Arbitrage paths visualization saved as 'arbitrage_paths.png'")

async def run_arbitrage_bot():
    try:
        logger.info("Starting arbitrage bot...")
        start_time = datetime.now()
        end_time = start_time + timedelta(hours=2)  # Run for 2 hours
        
        all_opportunities = []
        executed_opportunities = []
        
        while datetime.now() < end_time:
            await main_loop(all_opportunities, executed_opportunities)
            await asyncio.sleep(SCAN_INTERVAL)
        
        total_runtime = datetime.now() - start_time
        logger.info("Arbitrage bot run completed.")
        logger.info(f"Total runtime: {total_runtime}")
        logger.info(f"Total opportunities found: {len(all_opportunities)}")
        logger.info(f"Total executed opportunities: {len(executed_opportunities)}")
        
        # Visualize the arbitrage paths
        if all_opportunities:
            visualize_arbitrage_paths(all_opportunities)
        
        # Generate and save a detailed report
        report = generate_detailed_report(all_opportunities, executed_opportunities, total_runtime)
        with open('arbitrage_report.txt', 'w') as f:
            f.write(report)
        logger.info("Detailed report saved to 'arbitrage_report.txt'")
        
    except Exception as e:
        logger.error(f"Unexpected error in main execution: {str(e)}")
        logger.exception("Full traceback:")

def generate_detailed_report(all_opportunities, executed_opportunities, runtime):
    report = [
        f"Arbitrage Bot Detailed Report",
        f"==============================",
        f"",
        f"Total runtime: {runtime}",
        f"Total opportunities found: {len(all_opportunities)}",
        f"Total executed opportunities: {len(executed_opportunities)}",
        f"",
        f"Detailed Opportunities:",
        f"----------------------"
    ]
    
    for idx, opp in enumerate(all_opportunities, 1):
        report.extend([
            f"Opportunity {idx}:",
            f"  Type: {opp['type']}",
            f"  Token: {get_token_symbol(opp['token']) if 'token' in opp else 'N/A'}",
            f"  {'Deviation' if opp['type'] == 'price_deviation' else 'Imbalance'}: {opp.get('deviation', opp.get('imbalance', 'N/A')):.4f}",
            f"  Pool: {opp.get('pool', 'N/A')}",
            f"  Simulation Success: {opp['simulation_result']['success']}",
            f"  Simulated Profit: {opp['simulated_profit']} WETH",
            f"  Simulated Profit Percentage: {opp['simulation_result'].get('profit_percentage', 'N/A'):.2f}%",
            f"  Execution Success: {opp['success']}",
            f"  Actual Profit: {Web3.from_wei(opp['actual_profit'], 'ether') if opp['actual_profit'] else 'N/A'} WETH",
        ])
        
        if not opp['simulation_result']['success']:
            report.append(f"  Simulation Error: {opp['simulation_result'].get('error', 'Unknown')}")
            report.append(f"  Simulation Traceback: {opp['simulation_result'].get('traceback', 'N/A')}")
        
        if not opp['success'] and opp['receipt']:
            report.append(f"  Execution Error: Transaction reverted")
            report.append(f"  Transaction Hash: {opp['receipt']['transactionHash'].hex()}")
        
        report.append("")
    
    report.extend([
        f"Executed Opportunities:",
        f"------------------------"
    ])
    for idx, opp in enumerate(executed_opportunities, 1):
        report.extend([
            f"Executed Opportunity {idx}:",
            f"  Type: {opp['type']}",
            f"  Token: {get_token_symbol(opp['token']) if 'token' in opp else 'N/A'}",
            f"  Simulated Profit: {opp['simulated_profit']} WETH",
            f"  Actual Profit: {Web3.from_wei(opp['actual_profit'], 'ether')} WETH",
            f"  Transaction Hash: {opp['receipt']['transactionHash'].hex()}",
            f"  Gas Used: {opp['receipt']['gasUsed']}",
            ""
        ])
    
    report.extend([
        f"Summary:",
        f"--------",
        f"Success Rate: {len(executed_opportunities) / len(all_opportunities) * 100:.2f}%",
        f"Average Simulated Profit: {sum(opp['simulated_profit'] for opp in all_opportunities) / len(all_opportunities):.6f} WETH",
        f"Average Actual Profit: {sum(Web3.from_wei(opp['actual_profit'], 'ether') for opp in executed_opportunities) / len(executed_opportunities) if executed_opportunities else 'N/A'} WETH",
        f"Most Common Failure Reason: {get_most_common_failure_reason(all_opportunities)}",
    ])
    
    return "\n".join(report)

def get_most_common_failure_reason(opportunities):
    failure_reasons = [opp['simulation_result'].get('error', 'Unknown') for opp in opportunities if not opp['success']]
    if not failure_reasons:
        return "N/A"
    return max(set(failure_reasons), key=failure_reasons.count)

if __name__ == "__main__":
    asyncio.run(run_arbitrage_bot())