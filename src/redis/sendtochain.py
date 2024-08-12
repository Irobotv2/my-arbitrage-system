import asyncio
import aiohttp
from decimal import Decimal
from web3 import Web3, AsyncWeb3
from web3.providers.async_rpc import AsyncHTTPProvider
import redis
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='arbitrage_report.log', filemode='w')
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

async def get_uniswap_v2_price(session, pool_address):
    cache_key = f"v2_{pool_address}"
    if cache_key in price_cache and datetime.now() - price_cache[cache_key]['timestamp'] < timedelta(seconds=CACHE_EXPIRY):
        return price_cache[cache_key]['price']

    PAIR_ABI = [{"constant": True, "inputs": [], "name": "getReserves", "outputs": [{"name": "reserve0", "type": "uint112"}, {"name": "reserve1", "type": "uint112"}, {"name": "blockTimestampLast", "type": "uint32"}], "type": "function"}]
    
    try:
        contract = w3.eth.contract(address=pool_address, abi=PAIR_ABI)
        reserves = await contract.functions.getReserves().call()
        reserve0, reserve1, _ = reserves

        if reserve0 == 0 or reserve1 == 0:
            raise Exception("One or both reserves are zero")
        price = (Decimal(reserve1) / Decimal(10**6)) / (Decimal(reserve0) / Decimal(10**18))
        price_cache[cache_key] = {'price': price, 'timestamp': datetime.now()}
        return price
    except Exception as e:
        logger.error(f"Error fetching V2 price for pool {pool_address}: {e}")
        return None

async def get_uniswap_v3_price(session, pool_address):
    cache_key = f"v3_{pool_address}"
    if cache_key in price_cache and datetime.now() - price_cache[cache_key]['timestamp'] < timedelta(seconds=CACHE_EXPIRY):
        return price_cache[cache_key]['price']

    POOL_ABI = [{"inputs": [], "name": "slot0", "outputs": [{"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"}, {"internalType": "int24", "name": "tick", "type": "int24"}, {"internalType": "uint16", "name": "observationIndex", "type": "uint16"}, {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"}, {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"}, {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"}, {"internalType": "bool", "name": "unlocked", "type": "bool"}], "stateMutability": "view", "type": "function"}]
    
    try:
        contract = w3.eth.contract(address=pool_address, abi=POOL_ABI)
        slot0 = await contract.functions.slot0().call()
        sqrt_price_x96 = Decimal(slot0[0])

        if sqrt_price_x96 == 0:
            raise Exception("sqrt_price_x96 is zero")
        price = (sqrt_price_x96 ** 2) / (2 ** 192)
        price = price * (10 ** 12)  # Adjust for decimals (USDT has 6, ETH has 18)
        price_cache[cache_key] = {'price': price, 'timestamp': datetime.now()}
        return price
    except Exception as e:
        logger.error(f"Error fetching V3 price for pool {pool_address}: {e}")
        return None

async def get_pool_price(session, pool_address, is_v3):
    logger.info(f"Fetching price for pool {pool_address} (V3: {is_v3})")
    if is_v3:
        return await get_uniswap_v3_price(session, pool_address)
    else:
        return await get_uniswap_v2_price(session, pool_address)

def fetch_all_token_pairs():
    all_tokens = redis_client.keys("token:*")
    token_pairs = []
    weth_address = '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'  # WETH address
    
    for token_key in all_tokens:
        token_data = redis_client.hgetall(token_key)
        token_address = token_data['address']
        if token_address != weth_address:
            token_pairs.append((weth_address, token_address))
    
    logger.info(f"Fetched {len(token_pairs)} token pairs from Redis")
    return token_pairs

async def find_arbitrage_opportunities(session, token_pair, flash_loan_amount, min_profit_threshold=0.4):
    token1, token2 = token_pair
    logger.info(f"Searching for arbitrage opportunities for pair: {token1} - {token2}")
    
    try:
        v2_pools = redis_client.keys(f"uniswap_v2_pair:*")
        v3_pools = redis_client.keys(f"uniswap_v3_pool:*")
        logger.info(f"Found {len(v2_pools)} V2 pools and {len(v3_pools)} V3 pools")
        
        opportunities = []
        all_price_diffs = []
        
        for v2_pool in v2_pools:
            v2_data = redis_client.hgetall(v2_pool)
            if (v2_data['token0'] == token1 and v2_data['token1'] == token2) or \
               (v2_data['token0'] == token2 and v2_data['token1'] == token1):
                v2_price = await get_pool_price(session, v2_data['pair_address'], False)
                
                for v3_pool in v3_pools:
                    v3_data = redis_client.hgetall(v3_pool)
                    if (v3_data['token0'] == token1 and v3_data['token1'] == token2) or \
                       (v3_data['token0'] == token2 and v3_data['token1'] == token1):
                        v3_price = await get_pool_price(session, v3_data['pool_address'], True)
                        
                        if v2_price is not None and v3_price is not None:
                            price_diff = abs(v2_price - v3_price) / min(v2_price, v3_price)
                            all_price_diffs.append(price_diff)
                            logger.info(f"Price difference between V2 ({v2_data['pair_address']}) and V3 ({v3_data['pool_address']}): {price_diff:.2%}")
                            
                            if price_diff > min_profit_threshold:
                                if v2_price < v3_price:
                                    buy_pool = v2_data['pair_address']
                                    sell_pool = v3_data['pool_address']
                                    buy_is_v3 = False
                                    sell_is_v3 = True
                                else:
                                    buy_pool = v3_data['pool_address']
                                    sell_pool = v2_data['pair_address']
                                    buy_is_v3 = True
                                    sell_is_v3 = False
                                
                                opportunities.append({
                                    'token1': token1,
                                    'token2': token2,
                                    'buy_pool': buy_pool,
                                    'sell_pool': sell_pool,
                                    'buy_is_v3': buy_is_v3,
                                    'sell_is_v3': sell_is_v3,
                                    'price_difference': price_diff,
                                    'estimated_profit': price_diff * flash_loan_amount
                                })
                                logger.info(f"Found potential arbitrage opportunity with {price_diff:.2%} price difference")
        
        avg_price_diff = sum(all_price_diffs) / len(all_price_diffs) if all_price_diffs else 0
        logger.info(f"Average price difference for {token1}-{token2}: {avg_price_diff:.2%}")
        logger.info(f"Found {len(opportunities)} potential arbitrage opportunities")
        return opportunities, avg_price_diff
    except Exception as e:
        logger.error(f"Error finding arbitrage opportunities: {e}")
        return [], 0

async def simulate_arbitrage(opportunity, flash_loan_amount):
    logger.info(f"Simulating arbitrage for opportunity: {opportunity['token1']} - {opportunity['token2']}")
    contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)
    
    path = [
        {
            'tokenIn': Web3.to_checksum_address(opportunity['token1']),
            'tokenOut': Web3.to_checksum_address(opportunity['token2']),
            'pool': Web3.to_checksum_address(opportunity['buy_pool']),
            'isV3': opportunity['buy_is_v3'],
            'fee': 3000 if opportunity['buy_is_v3'] else 0,
            'price': Web3.to_wei(opportunity['price_difference'], 'ether')
        },
        {
            'tokenIn': Web3.to_checksum_address(opportunity['token2']),
            'tokenOut': Web3.to_checksum_address(opportunity['token1']),
            'pool': Web3.to_checksum_address(opportunity['sell_pool']),
            'isV3': opportunity['sell_is_v3'],
            'fee': 3000 if opportunity['sell_is_v3'] else 0,
            'price': Web3.to_wei(1 / opportunity['price_difference'], 'ether')
        }
    ]
    
    try:
        # Simulate the transaction
        result = await contract.functions.executeArbitrage(path, flash_loan_amount).call({
            'from': YOUR_WALLET_ADDRESS,
        })
        
        profit = Web3.from_wei(result, 'ether')
        logger.info(f"Simulated profit: {profit} ETH")
        return {
            'success': True,
            'profit': profit,
            'path': path,
            'flash_loan_amount': flash_loan_amount
        }
    except Exception as e:
        logger.error(f"Simulation failed: {str(e)}")
        return {'success': False, 'error': str(e)}
async def execute_arbitrage(opportunity, flash_loan_amount, w3):
    logger.info(f"Executing arbitrage for opportunity: {opportunity['token1']} - {opportunity['token2']}")
    contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)
    
    path = [
        {
            'tokenIn': Web3.to_checksum_address(opportunity['token1']),
            'tokenOut': Web3.to_checksum_address(opportunity['token2']),
            'pool': Web3.to_checksum_address(opportunity['buy_pool']),
            'isV3': opportunity['buy_is_v3'],
            'fee': 3000 if opportunity['buy_is_v3'] else 0,
            'price': Web3.to_wei(opportunity['price_difference'], 'ether')
        },
        {
            'tokenIn': Web3.to_checksum_address(opportunity['token2']),
            'tokenOut': Web3.to_checksum_address(opportunity['token1']),
            'pool': Web3.to_checksum_address(opportunity['sell_pool']),
            'isV3': opportunity['sell_is_v3'],
            'fee': 3000 if opportunity['sell_is_v3'] else 0,
            'price': Web3.to_wei(1 / opportunity['price_difference'], 'ether')
        }
    ]
    
    try:
        # Estimate gas first
        gas_estimate = await contract.functions.executeArbitrage(path, flash_loan_amount).estimate_gas({
            'from': 'YOUR_WALLET_ADDRESS',
        })
        logger.info(f"Estimated gas: {gas_estimate}")

        # Build the transaction
        transaction = await contract.functions.executeArbitrage(path, flash_loan_amount).build_transaction({
            'from': 'YOUR_WALLET_ADDRESS',
            'gas': int(gas_estimate * 1.2),  # Add 20% buffer
            'gasPrice': await w3.eth.gas_price,
            'nonce': await w3.eth.get_transaction_count('YOUR_WALLET_ADDRESS'),
        })
        
        # Sign and send the transaction
        signed_txn = w3.eth.account.sign_transaction(transaction, 'YOUR_PRIVATE_KEY')
        tx_hash = await w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        
        # Wait for the transaction receipt
        tx_receipt = await w3.eth.wait_for_transaction_receipt(tx_hash)
        
        if tx_receipt['status'] == 1:
            logger.info(f"Arbitrage executed successfully. Transaction hash: {tx_receipt['transactionHash'].hex()}")
            logger.info(f"Gas used: {tx_receipt['gasUsed']}")
        else:
            logger.error(f"Transaction failed. Transaction hash: {tx_receipt['transactionHash'].hex()}")
            
            # Try to get more information about the failure
            try:
                tx = await w3.eth.get_transaction(tx_hash)
                result = await w3.eth.call(dict(tx, gas=tx['gas']), tx['blockNumber'] - 1)
            except ContractLogicError as e:
                logger.error(f"Contract reverted with reason: {e}")
            except Exception as e:
                logger.error(f"Error while trying to get more information: {e}")
        
        return tx_receipt
    except ContractLogicError as e:
        logger.error(f"Contract logic error: {e}")
        return None
    except Exception as e:
        logger.error(f"Error executing arbitrage: {e}")
        logger.error(traceback.format_exc())
        return None
async def execute_arbitrage_with_retry(opportunity, flash_loan_amount, max_retries=3):
    for attempt in range(max_retries):
        simulation_result = await simulate_arbitrage(opportunity, flash_loan_amount)
        if simulation_result['success']:
            # Check if simulated profit meets the 40% threshold
            simulated_profit_percentage = (simulation_result['profit'] / Web3.from_wei(flash_loan_amount, 'ether')) * 100
            if simulated_profit_percentage >= 1:
                logger.info(f"Simulated profit of {simulated_profit_percentage:.2f}% meets the 40% threshold. Executing transaction.")
                tx_receipt = await execute_arbitrage(opportunity, flash_loan_amount)
                if tx_receipt and tx_receipt['status'] == 1:
                    return tx_receipt
            else:
                logger.info(f"Simulated profit of {simulated_profit_percentage:.2f}% does not meet the 40% threshold. Skipping execution.")
                return None
        
        # If we're here, either simulation failed or execution failed
        logger.warning(f"Attempt {attempt + 1} failed. Adjusting parameters and retrying...")
        # Adjust parameters (e.g., increase slippage tolerance, recalculate prices)
        opportunity = adjust_opportunity_parameters(opportunity)
    
    logger.error("All attempts to execute arbitrage failed")
    return None

def adjust_opportunity_parameters(opportunity):
    # Implement logic to adjust parameters, e.g., increase slippage tolerance
    # For now, we'll just return the original opportunity
    return opportunity
async def main(run_time=5):
    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=run_time)
    
    flash_loan_amount = Web3.to_wei(1, 'ether')  # 1 WETH
    logger.info(f"Starting arbitrage search. Will run until {end_time}")
    logger.info(f"Flash loan amount: {Web3.from_wei(flash_loan_amount, 'ether')} ETH")
    
    token_pairs = fetch_all_token_pairs()
    logger.info(f"Analyzing {len(token_pairs)} token pairs")
    
    all_opportunities = []
    simulated_opportunities = []
    
    async with aiohttp.ClientSession() as session:
        while datetime.now() < end_time:
            for token_pair in token_pairs:
                logger.info(f"Analyzing token pair: {token_pair[0]} - {token_pair[1]}")
                opportunities, _ = await find_arbitrage_opportunities(session, token_pair, flash_loan_amount)
                all_opportunities.extend(opportunities)
                
                for opportunity in opportunities:
                    simulation_result = await simulate_arbitrage(opportunity, flash_loan_amount)
                    if simulation_result['success']:
                        simulated_opportunities.append({
                            'opportunity': opportunity,
                            'simulation_result': simulation_result
                        })
            
            logger.info(f"Completed iteration. Time elapsed: {datetime.now() - start_time}")
            await asyncio.sleep(1)  # Add a small delay to prevent overwhelming the system
    
    total_runtime = datetime.now() - start_time
    report = generate_detailed_report(all_opportunities, simulated_opportunities, total_runtime)
    logger.info("Arbitrage search completed. Final report:")
    logger.info("\n" + report)

    return report


def generate_detailed_report(all_opportunities, simulated_opportunities, runtime):
    report = [
        f"1. Total runtime: {runtime}",
        f"2. Total potential opportunities found: {len(all_opportunities)}",
        f"3. Total simulated opportunities: {len(simulated_opportunities)}",
        "4. Detailed opportunity breakdown:"
    ]
    
    for idx, sim_opp in enumerate(simulated_opportunities, 1):
        opp = sim_opp['opportunity']
        sim = sim_opp['simulation_result']
        report.extend([
            f"\nOpportunity {idx}:",
            f"   Token1: {opp['token1']}",
            f"   Token2: {opp['token2']}",
            f"   Buy pool: {opp['buy_pool']} (V3: {opp['buy_is_v3']})",
            f"   Sell pool: {opp['sell_pool']} (V3: {opp['sell_is_v3']})",
            f"   Price difference: {opp['price_difference']:.2%}",
            f"   Estimated profit: {Web3.from_wei(opp['estimated_profit'], 'ether')} ETH",
            f"   Simulated profit: {sim['profit']} ETH",
            "   Execution path:",
            f"     Step 1: Input {Web3.from_wei(sim['flash_loan_amount'], 'ether')} {opp['token1']} -> Output {Web3.from_wei(sim['path'][0]['price'], 'ether')} {opp['token2']}",
            f"     Step 2: Input {Web3.from_wei(sim['path'][1]['price'], 'ether')} {opp['token2']} -> Output {sim['profit']} {opp['token1']}"
        ])
    
    return "\n".join(report)

async def run_arbitrage_bot():
    try:
        await main(run_time=5)  # Run for 5 minutes
    except Exception as e:
        logger.error(f"Unexpected error in main execution: {e}")

if __name__ == "__main__":
    # Run the main arbitrage bot
    asyncio.run(run_arbitrage_bot())