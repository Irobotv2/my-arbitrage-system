import time
import json
import logging
from decimal import Decimal, getcontext, InvalidOperation
from web3.exceptions import ContractLogicError  # Add this line
from web3 import Web3
from web3.middleware import geth_poa_middleware
import redis
import requests
from eth_account.messages import encode_defunct
from eth_account import Account
from eth_abi.abi import encode


# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Web3 and Redis
w3_local = Web3(Web3.HTTPProvider('http://localhost:8545'))
w3_exec = Web3(Web3.HTTPProvider('http://localhost:8545'))
w3_exec.middleware_onion.inject(geth_poa_middleware, layer=0)
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Configuration
WALLET_ADDRESS = "0x6f2F4f0210AC805D817d4CD0b9A4D0c29d232E93"
PRIVATE_KEY = "6575ac283b8aa1cbd913d2d28557e318048f8e62a5a19a74001988e2f40ab06c"
FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS = "0x26B7B5AB244114ab88578D5C4cD5b096097bf543"
UNISWAP_V2_ROUTER_ADDRESS = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
UNISWAP_V3_ROUTER_ADDRESS = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
V3_QUOTER_ADDRESS = "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6"
DETECTION_THRESHOLD = 0.005  # 0.5%
EXECUTION_THRESHOLD = 0.01   # 1%
GAS_PRICE = 20  # Gwei
FLASH_LOAN_FEE = Decimal('0.0009')  # 0.09%

# ABIs
V2_POOL_ABI = [{"constant":True,"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"stateMutability":"view","type":"function"}]

UNISWAP_V2_ROUTER_ABI = [{"name":"getAmountsOut","type":"function","inputs":[{"name":"amountIn","type":"uint256"},{"name":"path","type":"address[]"}],"outputs":[{"name":"amounts","type":"uint256[]"}],"stateMutability":"view"},{"name":"swapExactTokensForTokens","type":"function","inputs":[{"name":"amountIn","type":"uint256"},{"name":"amountOutMin","type":"uint256"},{"name":"path","type":"address[]"},{"name":"to","type":"address"},{"name":"deadline","type":"uint256"}],"outputs":[{"name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable"}]

V3_POOL_ABI = [{"inputs":[],"name":"slot0","outputs":[{"internalType":"uint160","name":"sqrtPriceX96","type":"uint160"},{"internalType":"int24","name":"tick","type":"int24"},{"internalType":"uint16","name":"observationIndex","type":"uint16"},{"internalType":"uint16","name":"observationCardinality","type":"uint16"},{"internalType":"uint16","name":"observationCardinalityNext","type":"uint16"},{"internalType":"uint8","name":"feeProtocol","type":"uint8"},{"internalType":"bool","name":"unlocked","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"liquidity","outputs":[{"internalType":"uint128","name":"","type":"uint128"}],"stateMutability":"view","type":"function"}]

UNISWAP_V3_ROUTER_ABI = [{"name":"exactInputSingle","type":"function","inputs":[{"name":"params","type":"tuple","components":[{"name":"tokenIn","type":"address"},{"name":"tokenOut","type":"address"},{"name":"fee","type":"uint24"},{"name":"recipient","type":"address"},{"name":"deadline","type":"uint256"},{"name":"amountIn","type":"uint256"},{"name":"amountOutMinimum","type":"uint256"},{"name":"sqrtPriceLimitX96","type":"uint160"}]}],"outputs":[{"name":"amountOut","type":"uint256"}],"stateMutability":"payable"}]

V3_QUOTER_ABI = [{"inputs":[{"internalType":"bytes","name":"path","type":"bytes"},{"internalType":"uint256","name":"amountIn","type":"uint256"}],"name":"quoteExactInput","outputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"uint160[]","name":"sqrtPriceX96AfterList","type":"uint160[]"},{"internalType":"uint32[]","name":"initializedTicksCrossedList","type":"uint32[]"},{"internalType":"uint256","name":"gasEstimate","type":"uint256"}],"stateMutability":"nonpayable","type":"function"}]

ERC20_ABI = [{"constant":True,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"},{"constant":False,"inputs":[{"name":"_spender","type":"address"},{"name":"_value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"type":"function"}]

# Helper Functions
def load_configurations_from_redis():
    configs = {}
    for key in redis_client.keys('*_config'):
        config_json = redis_client.get(key)
        config = json.loads(config_json)
        configs[key.decode('utf-8')] = config
    return configs

def get_token_decimals(token_address):
    token_contract = w3_local.eth.contract(address=token_address, abi=ERC20_ABI)
    return token_contract.functions.decimals().call()

def get_v2_quote(router_contract, amount_in, token_in, token_out):
    try:
        quote = router_contract.functions.getAmountsOut(
            amount_in,
            [token_in, token_out]
        ).call()
        return quote[1]
    except Exception as e:
        logger.error(f"Error getting V2 quote: {str(e)}")
        return None

def get_v3_quote(quoter_contract, amount_in, token_in, token_out, fee):
    try:
        path = encode(['address', 'uint24', 'address'], [token_in, fee, token_out])
        logger.debug(f"Querying V3 quote with: amount_in={amount_in}, token_in={token_in}, token_out={token_out}, fee={fee}")
        quote = quoter_contract.functions.quoteExactInput(path, amount_in).call()
        logger.debug(f"V3 quote result: {quote}")
        return quote[0]
    except ContractLogicError as cle:
        logger.error(f"Contract logic error in V3 quote: {str(cle)}")
        return None
    except ValueError as ve:
        if "execution reverted" in str(ve):
            logger.error(f"Execution reverted in V3 quote: {str(ve)}")
        else:
            logger.error(f"Value error in V3 quote: {str(ve)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in V3 quote: {str(e)}")
        return None

def calculate_price_difference(amount_in, v2_amount_out, v3_amount_out):
    if v2_amount_out is None or v3_amount_out is None:
        return None
    v2_price = Decimal(amount_in) / Decimal(v2_amount_out)
    v3_price = Decimal(amount_in) / Decimal(v3_amount_out)
    return abs(v2_price - v3_price) / min(v2_price, v3_price)


def validate_tokens_and_pools(token0, token1, v2_pool, v3_pools):
    # Validate token addresses
    if not w3_local.is_address(token0['address']) or not w3_local.is_address(token1['address']):
        logger.error(f"Invalid token addresses: token0={token0['address']}, token1={token1['address']}")
        return False

    # Validate V2 pool
    if v2_pool and not w3_local.is_address(v2_pool):
        logger.error(f"Invalid V2 pool address: {v2_pool}")
        return False

    # Validate V3 pools
    for fee_tier, pool_info in v3_pools.items():
        if not w3_local.is_address(pool_info['address']):
            logger.error(f"Invalid V3 pool address for fee tier {fee_tier}: {pool_info['address']}")
            return False

    return True

def convert_fee_tier(fee_tier_str):
    """
    Convert fee tier from percentage string to integer basis points.
    """
    try:
        # Remove '%' sign and convert to float
        fee_percentage = float(fee_tier_str.strip('%'))
        # Convert percentage to basis points (multiply by 100)
        return int(fee_percentage * 100)
    except ValueError:
        logger.error(f"Invalid fee tier format: {fee_tier_str}")
        return None

def detect_arbitrage(w3, v2_router_address, v3_quoter_address, token_in, token_out, amount_in, v3_fee_str):
    v2_router = w3.eth.contract(address=v2_router_address, abi=UNISWAP_V2_ROUTER_ABI)
    v3_quoter = w3.eth.contract(address=v3_quoter_address, abi=V3_QUOTER_ABI)

    v3_fee = convert_fee_tier(v3_fee_str)
    if v3_fee is None:
        logger.error(f"Invalid V3 fee tier: {v3_fee_str}")
        return None

    logger.debug(f"Querying V2 quote for {token_in} to {token_out} with amount {amount_in}")
    v2_quote = get_v2_quote(v2_router, amount_in, token_in, token_out)
    if v2_quote is None:
        logger.error("Failed to get V2 quote")
        return None

    logger.debug(f"Querying V3 quote for {token_in} to {token_out} with amount {amount_in} and fee {v3_fee}")
    v3_quote = get_v3_quote(v3_quoter, amount_in, token_in, token_out, v3_fee)
    if v3_quote is None:
        logger.error("Failed to get V3 quote")
        return None

    price_difference = calculate_price_difference(amount_in, v2_quote, v3_quote)
    
    if price_difference is not None and price_difference > DETECTION_THRESHOLD:
        logger.info(f"Arbitrage opportunity detected: V2 quote: {v2_quote}, V3 quote: {v3_quote}, Price difference: {price_difference:.2%}")
        return {
            'v2_quote': v2_quote,
            'v3_quote': v3_quote,
            'price_difference': price_difference
        }
    return None

def calculate_optimal_flashloan_amount(pool_address, price_difference):
    try:
        pool_contract = w3_local.eth.contract(address=pool_address, abi=V3_POOL_ABI)
        liquidity = pool_contract.functions.liquidity().call()
        max_amount = Decimal(w3_exec.from_wei(liquidity, 'ether'))
        price_difference_decimal = Decimal(str(price_difference))
        optimal_amount = max(min(max_amount * (price_difference_decimal / Decimal('100')), Decimal('100')), Decimal('1'))
        logger.info(f"Calculated optimal flash loan amount: {optimal_amount}")
        return optimal_amount
    except Exception as e:
        logger.error(f"Error calculating optimal flash loan amount: {str(e)}")
        return Decimal('1')  # Return a default amount if calculation fails

def construct_arbitrage_path(start_token, amount, path):
    try:
        current_amount = Decimal(str(amount))
    except Exception as e:
        logger.error(f"Error converting start amount to decimal: {str(e)}")
        return None

    result = [f"1. Borrow {current_amount:.8f} {start_token}"]

    for i, (from_token, to_token, pool_address, is_v3) in enumerate(path):
        # Implement the logic to get quotes and construct the path
        # This is a placeholder and should be implemented based on your specific requirements
        result.append(f"{i+2}. Swap {from_token} to {to_token}")

    return result

def build_flashbots_bundle(arbitrage_path, wallet_address):
    # Implement the logic to build the Flashbots bundle
    # This is a placeholder and should be implemented based on your specific requirements
    return []

def send_bundle_to_builders(bundle):
    bundle_json = json.dumps(bundle, separators=(',', ':'))
    message = encode_defunct(text=bundle_json)
    signed_message = Account.sign_message(message, private_key=PRIVATE_KEY)
    flashbots_signature = f"{WALLET_ADDRESS}:{signed_message.signature.hex()}"

    for url in builder_urls:
        try:
            headers = {
                "Content-Type": "application/json",
                "X-Flashbots-Signature": flashbots_signature
            }

            logger.info(f"Sending bundle to {url}")
            response = requests.post(url, json=bundle, headers=headers)

            if response.status_code == 200:
                logger.info(f"Bundle sent successfully to {url}: {response.json()}")
            else:
                logger.warning(f"Failed to send bundle to {url}: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Error sending bundle to {url}: {str(e)}")

def send_bundle(transaction_bundle):
    bundle = {
        "method": "eth_sendBundle",
        "params": [transaction_bundle],
        "id": 1,
        "jsonrpc": "2.0"
    }

    logger.info(f"Crafted bundle for submission: {json.dumps(bundle, indent=2)}")
    send_bundle_to_builders(bundle)

def monitor_and_execute_arbitrage():
    logger.info("Starting arbitrage monitoring...")
    configurations = load_configurations_from_redis()
    
    while True:
        for config_name, config in configurations.items():
            try:
                logger.debug(f"Processing configuration: {config_name}")
                token0 = config['token0']
                token1 = config['token1']
                v2_pool = config.get('v2_pool')
                v3_pools = config.get('v3_pools', {})
                
                if not validate_tokens_and_pools(token0, token1, v2_pool, v3_pools):
                    logger.error(f"Invalid configuration for {config_name}. Skipping.")
                    continue

                # Use a fixed amount for quote (e.g., 1 ETH worth)
                amount_in = w3_local.to_wei(1, 'ether')
                
                if v2_pool:
                    for fee_tier_str, v3_pool_info in v3_pools.items():
                        logger.debug(f"Checking arbitrage for {config_name} with V3 fee tier {fee_tier_str}")
                        arbitrage_result = detect_arbitrage(
                            w3_local,
                            UNISWAP_V2_ROUTER_ADDRESS,
                            V3_QUOTER_ADDRESS,
                            token0['address'],
                            token1['address'],
                            amount_in,
                            fee_tier_str
                        )
                        
                        if arbitrage_result:
                            logger.info(f"Arbitrage opportunity detected for {config_name}")
                            logger.info(f"V2 Quote: {arbitrage_result['v2_quote']}, V3 Quote: {arbitrage_result['v3_quote']}")
                            logger.info(f"Price Difference: {arbitrage_result['price_difference']:.2%}")
                            
                            if arbitrage_result['price_difference'] > EXECUTION_THRESHOLD:
                                logger.info(f"Executing arbitrage for {config_name}")
                                try:
                                    # Determine direction of arbitrage
                                    is_v2_to_v3 = arbitrage_result['v2_quote'] < arbitrage_result['v3_quote']
                                    
                                    # Calculate optimal flash loan amount
                                    flash_loan_amount = calculate_optimal_flashloan_amount(
                                        v3_pool_info['address'], 
                                        float(arbitrage_result['price_difference'])
                                    )
                                    
                                    # Construct arbitrage path
                                    path = [
                                        (token0['symbol'], token1['symbol'], v2_pool, False),
                                        (token1['symbol'], token0['symbol'], v3_pool_info['address'], True)
                                    ] if is_v2_to_v3 else [
                                        (token1['symbol'], token0['symbol'], v3_pool_info['address'], True),
                                        (token0['symbol'], token1['symbol'], v2_pool, False)
                                    ]
                                    
                                    arbitrage_details = construct_arbitrage_path(
                                        token0['symbol'] if is_v2_to_v3 else token1['symbol'],
                                        flash_loan_amount,
                                        path
                                    )
                                    
                                    if arbitrage_details:
                                        logger.info("Arbitrage path constructed:")
                                        for step in arbitrage_details:
                                            logger.info(step)
                                        
                                        # Build and send Flashbots bundle
                                        bundle = build_flashbots_bundle(arbitrage_details, WALLET_ADDRESS)
                                        if bundle:
                                            transaction_bundle = [{
                                                "signedTransaction": w3_local.eth.account.sign_transaction(tx, PRIVATE_KEY).rawTransaction.hex()
                                                for tx in bundle
                                            }]
                                            send_bundle(transaction_bundle)
                                            logger.info("Arbitrage execution attempted. Check logs for confirmation.")
                                        else:
                                            logger.warning("Failed to build Flashbots bundle")
                                    else:
                                        logger.warning("Failed to construct arbitrage path")
                                except Exception as exec_error:
                                    logger.error(f"Error executing arbitrage: {str(exec_error)}")
                            else:
                                logger.info(f"Opportunity detected but below execution threshold for {config_name}")
                else:
                    logger.debug(f"No V2 pool found for {config_name}. Skipping.")
            except Exception as e:
                logger.error(f"Error processing configuration {config_name}: {str(e)}")
        
        logger.debug("Sleeping before next iteration...")
        time.sleep(1)  # Adjust the sleep time as needed
# Main execution
if __name__ == "__main__":
    logger.info("Starting arbitrage bot...")
    try:
        monitor_and_execute_arbitrage()
    except KeyboardInterrupt:
        logger.info("Arbitrage bot stopped by user.")
    except Exception as e:
        logger.error(f"Unexpected error occurred: {str(e)}")
    finally:
        logger.info("Arbitrage bot shutting down.")