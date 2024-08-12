import asyncio
import aiohttp
from decimal import Decimal
from web3 import Web3, AsyncWeb3
from web3.providers.async_rpc import AsyncHTTPProvider
from web3.middleware import geth_poa_middleware
import redis
import logging
from datetime import datetime, timedelta
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='arbitrage_report.log', filemode='w')
logger = logging.getLogger()
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
logger.addHandler(console_handler)

# Initialize Redis client
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Initialize Web3 with multiple providers
providers = [
    AsyncHTTPProvider('https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c'),
    AsyncHTTPProvider('https://mainnet.infura.io/v3/0640f56f05a942d7a25cfeff50de344d'),
    AsyncHTTPProvider('http://localhost:8545'),  # Local node
]

async def get_working_web3():
    for provider in providers:
        w3 = AsyncWeb3(provider)
        try:
            await w3.eth.get_block_number()
            logger.info(f"Connected to {provider.endpoint_uri}")
            return w3
        except Exception as e:
            logger.warning(f"Failed to connect to {provider.endpoint_uri}: {e}")
    raise Exception("No working Web3 provider found")

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
        "name": "simulateArbitrage",
        "outputs": [
            {"internalType": "uint256", "name": "estimatedProfit", "type": "uint256"},
            {"internalType": "uint256[]", "name": "simulationResults", "type": "uint256[]"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

CONTRACT_ADDRESS = Web3.to_checksum_address("0x48334a214155101522519c5f6c2d82e46cb405d4")

# Price cache
price_cache = {}
CACHE_EXPIRY = 30  # seconds

async def get_uniswap_v2_price(session, pool_address, w3):
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

async def get_uniswap_v3_price(session, pool_address, w3):
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

async def get_pool_price(session, pool_address, is_v3, w3):
    logger.info(f"Fetching price for pool {pool_address} (V3: {is_v3})")
    if is_v3:
        return await get_uniswap_v3_price(session, pool_address, w3)
    else:
        return await get_uniswap_v2_price(session, pool_address, w3)

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

async def find_arbitrage_opportunities(session, token_pair, flash_loan_amount, w3, min_profit_threshold=0.005):
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
                v2_price = await get_pool_price(session, v2_data['pair_address'], False, w3)
                
                for v3_pool in v3_pools:
                    v3_data = redis_client.hgetall(v3_pool)
                    if (v3_data['token0'] == token1 and v3_data['token1'] == token2) or \
                       (v3_data['token0'] == token2 and v3_data['token1'] == token1):
                        v3_price = await get_pool_price(session, v3_data['pool_address'], True, w3)
                        
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

async def simulate_arbitrage(opportunity, flash_loan_amount, contract):
    logger.info(f"Simulating arbitrage for opportunity: {opportunity['token1']} - {opportunity['token2']}")
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
        estimated_profit, simulation_results = await contract.functions.simulateArbitrage(path, flash_loan_amount).call()
        
        logger.info(f"Simulation details for {opportunity['token1']} - {opportunity['token2']}:")
        logger.info(f"  Buy pool: {opportunity['buy_pool']} (V3: {opportunity['buy_is_v3']})")
        logger.info(f"  Sell pool: {opportunity['sell_pool']} (V3: {opportunity['sell_is_v3']})")
        logger.info(f"  Initial flash loan amount: {Web3.from_wei(flash_loan_amount, 'ether')} ETH")
        
        for i, result in enumerate(simulation_results):
            if i == 0:
                logger.info(f"  Step {i}: Flash loan received: {Web3.from_wei(result, 'ether')} ETH")
            elif i == len(simulation_results) - 1:
                logger.info(f"  Step {i}: Final amount after repaying flash loan: {Web3.from_wei(result, 'ether')} ETH")
            else:
                logger.info(f"  Step {i}: Intermediate amount: {Web3.from_wei(result, 'ether')} ETH")
        
        estimated_profit_eth = Web3.from_wei(estimated_profit, 'ether')
        logger.info(f"  Estimated profit: {estimated_profit_eth} ETH")
        logger.info(f"  Profit percentage: {(estimated_profit_eth / Web3.from_wei(flash_loan_amount, 'ether')) * 100:.2f}%")
        
        return Decimal(estimated_profit), simulation_results
    except Exception as e:
        logger.error(f"Error in simulate_arbitrage: {e}")
        return Decimal('0'), []

def generate_report(iterations, token_pairs, opportunities, best_opportunity, runtime, avg_price_diffs):
    report = [
        f"1. Total tokens analyzed: {len(token_pairs)}",
        f"2. Total iterations completed: {iterations}",
        f"3. Total runtime: {runtime}",
        f"4. Total potential opportunities found: {len(opportunities)}",
        f"5. Average price differences per token pair:",
    ]
    
    for pair, avg_diff in avg_price_diffs.items():
        report.append(f"   - {pair[0]}-{pair[1]}: {avg_diff:.2%}")
    
    report.append("6. Potential opportunities breakdown:")
    
    opportunity_counts = {}
    for o in opportunities:
        pair = (o['token1'], o['token2'])
        opportunity_counts[pair] = opportunity_counts.get(pair, 0) + 1
    
    for pair, count in opportunity_counts.items():
        report.append(f"   - {pair[0]}-{pair[1]}: {count}")
    
    if best_opportunity:
        report.extend([
            f"7. Highest profit opportunity:",
            f"   - Tokens: {best_opportunity['token1']}-{best_opportunity['token2']}",
            f"   - Buy pool: {best_opportunity['buy_pool']} (V3: {best_opportunity['buy_is_v3']})",
            f"   - Sell pool: {best_opportunity['sell_pool']} (V3: {best_opportunity['sell_is_v3']})",
            f"   - Price difference: {best_opportunity['price_difference']:.2%}",
            f"   - Estimated profit: {Web3.from_wei(best_opportunity['simulated_profit'], 'ether')} ETH"
        ])
    else:
        report.append("7. No profitable opportunities found after simulation")
    
    return "\n".join(report)

async def main(run_time=60):
    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=run_time)
    
    flash_loan_amount = Web3.to_wei(1, 'ether')  # 1 WETH
    logger.info(f"Starting arbitrage search. Will run until {end_time}")
    logger.info(f"Flash loan amount: {Web3.from_wei(flash_loan_amount, 'ether')} ETH")
    
    token_pairs = fetch_all_token_pairs()
    logger.info(f"Analyzing {len(token_pairs)} token pairs")
    
    best_opportunity = None
    highest_profit = Decimal('0')
    iterations = 0
    all_opportunities = []
    avg_price_diffs = {}
    
    async with aiohttp.ClientSession() as session:
        while datetime.now() < end_time:
            iterations += 1
            logger.info(f"Starting iteration {iterations}")
            
            try:
                w3 = await get_working_web3()
                contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)
                
                for token_pair in token_pairs:
                    logger.info(f"Analyzing token pair: {token_pair[0]} - {token_pair[1]}")
                    opportunities, avg_price_diff = await find_arbitrage_opportunities(session, token_pair, flash_loan_amount, w3)
                    all_opportunities.extend(opportunities)
                    avg_price_diffs[token_pair] = avg_price_diff
                    
                    for opportunity in opportunities:
                        estimated_profit, simulation_results = await simulate_arbitrage(opportunity, flash_loan_amount, contract)
                        
                        if estimated_profit > highest_profit:
                            highest_profit = estimated_profit
                            best_opportunity = opportunity
                            best_opportunity['simulated_profit'] = estimated_profit
                            best_opportunity['simulation_results'] = simulation_results
                
            except Exception as e:
                logger.error(f"Error in iteration {iterations}: {e}")
            
            logger.info(f"Completed iteration {iterations}. Time elapsed: {datetime.now() - start_time}")
            await asyncio.sleep(1)  # Add a small delay to prevent overwhelming the system
    
    total_runtime = datetime.now() - start_time
    report = generate_report(iterations, token_pairs, all_opportunities, best_opportunity, total_runtime, avg_price_diffs)
    logger.info("Arbitrage search completed. Final report:")
    logger.info("\n" + report)

    return report

async def run_arbitrage_bot():
    try:
        await main(run_time=5)  # Run for 5 minutes as a test
    except Exception as e:
        logger.error(f"Unexpected error in main execution: {e}")

if __name__ == "__main__":
    # Run the main arbitrage bot
    asyncio.run(run_arbitrage_bot())