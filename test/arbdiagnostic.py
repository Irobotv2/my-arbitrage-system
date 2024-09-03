import logging
from web3 import Web3
from decimal import Decimal
import json
import time

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Web3 setup
provider_url = 'http://localhost:8545'  # Replace with your Ethereum node URL
w3 = Web3(Web3.HTTPProvider(provider_url))

# ABIs
V2_POOL_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"internalType": "uint112", "name": "_reserve0", "type": "uint112"},
            {"internalType": "uint112", "name": "_reserve1", "type": "uint112"},
            {"internalType": "uint32", "name": "_blockTimestampLast", "type": "uint32"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

V3_POOL_ABI = [
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
    },
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function"
    }
]

ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    }
]

# Configuration
CONFIGURATIONS = {
    'stETH-WETH': {
        'name': 'stETH-WETH',
        'token0': {'address': '0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84'},  # stETH
        'token1': {'address': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'},  # WETH
        'v2_pool': '0x4028DAAC072e492d34a3Afdbef0ba7e35D8b55C4',
        'v3_pools': {
            '0.01%': {'address': '0x8f8eaaF88448ba31BdffF6aD8c42830c032C6392'},
            '0.05%': {'address': '0xeacDF56d530a4ec6639c2C86F1915F4956446b5C'},
            '0.30%': {'address': '0x301C755bA0fcA00B1923768Fffb3Df7f4E63cF31'},
            '1.00%': {'address': '0x7379e81228514a1D2a6Cf7559203998E20598346'},
        }
    },
    'WBTC-SHIB': {
        'name': 'WBTC-SHIB',
        'token0': {'address': '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599'},  # WBTC
        'token1': {'address': '0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE'},  # SHIB
        'v2_pool': '0x82b4d8bd5ba17ce5775f53a7d75b582d6d6ff082',  # Verify this address
        'v3_pools': {
            '1.00%': {'address': '0x0c9fe226d294b17bfcf0eccc28d344d507fe1c93'},
        }
    }
}

def get_token_decimals(token_address):
    token_contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
    return token_contract.functions.decimals().call()

def check_v2_pool_exists(pool_address):
    try:
        v2_pool_contract = w3.eth.contract(address=pool_address, abi=V2_POOL_ABI)
        reserves = v2_pool_contract.functions.getReserves().call()
        logging.info(f"V2 Pool {pool_address} exists with reserves: {reserves}")
        return True
    except Exception as e:
        logging.error(f"Error checking V2 pool {pool_address}: {str(e)}")
        return False

def get_price_v2(pool_contract, token0_decimals, token1_decimals):
    try:
        reserves = pool_contract.functions.getReserves().call()
        reserve0 = Decimal(reserves[0])
        reserve1 = Decimal(reserves[1])
        
        normalized_reserve0 = reserve0 / Decimal(10 ** token0_decimals)
        normalized_reserve1 = reserve1 / Decimal(10 ** token1_decimals)

        price = normalized_reserve1 / normalized_reserve0
        
        logging.info(f"V2 Price Calculation: reserve0={reserve0}, reserve1={reserve1}, "
                     f"normalized_reserve0={normalized_reserve0}, normalized_reserve1={normalized_reserve1}, "
                     f"price={price}")
        
        if price <= 0:
            logging.warning(f"V2 Price is zero or negative: {price}")
        
        return float(price)
    except Exception as e:
        logging.error(f"Error calculating V2 price: {str(e)}")
        return None

def check_v3_pool_liquidity(pool_address):
    v3_pool_contract = w3.eth.contract(address=pool_address, abi=V3_POOL_ABI)
    liquidity = v3_pool_contract.functions.liquidity().call()
    logging.info(f"V3 Pool {pool_address} liquidity: {liquidity}")
    return liquidity

def sqrt_price_x96_to_price(sqrt_price_x96, token0_decimals, token1_decimals):
    try:
        sqrt_price = Decimal(sqrt_price_x96) / Decimal(2 ** 96)
        price = sqrt_price ** 2
        decimal_adjustment = Decimal(10 ** (token1_decimals - token0_decimals))
        adjusted_price = price * decimal_adjustment
        
        logging.info(f"V3 Price Calculation: sqrt_price_x96={sqrt_price_x96}, "
                     f"sqrt_price={sqrt_price}, price={price}, "
                     f"decimal_adjustment={decimal_adjustment}, adjusted_price={adjusted_price}")
        
        if adjusted_price <= 0:
            logging.warning(f"V3 Price is zero or negative: {adjusted_price}")
        
        return float(adjusted_price)
    except Exception as e:
        logging.error(f"Error calculating V3 price: {str(e)}")
        return None

def get_price_v3(pool_contract, token0_decimals, token1_decimals):
    try:
        slot0_data = pool_contract.functions.slot0().call()
        sqrt_price_x96 = slot0_data[0]
        return sqrt_price_x96_to_price(sqrt_price_x96, token0_decimals, token1_decimals)
    except Exception as e:
        logging.error(f"Error getting V3 slot0 data: {str(e)}")
        return None

def validate_v3_price(price, fee_tier):
    if price is None:
        logging.warning(f"V3 price is None for {fee_tier} fee tier")
        return None
    if price < 1e-10 or price > 1e10:
        logging.warning(f"Unusual V3 price for {fee_tier} fee tier: {price}")
        return None
    return price

def is_valid_arbitrage_opportunity(price_v2, price_v3, profit_percentage):
    if price_v2 is None or price_v3 is None:
        return False
    if price_v2 <= 0 or price_v3 <= 0:
        return False
    if abs(profit_percentage) > 10:  # Adjust this threshold as needed
        logging.warning(f"Unusually high profit percentage: {profit_percentage}%")
        return False
    return True

def calculate_profit_percentage(price_v2, price_v3):
    if price_v2 is None or price_v3 is None:
        return None
    return abs(price_v2 - price_v3) / min(price_v2, price_v3) * 100

def diagnose_pair(config):
    logging.info(f"Diagnosing pair: {config['name']}")
    
    token0_decimals = get_token_decimals(config['token0']['address'])
    token1_decimals = get_token_decimals(config['token1']['address'])
    
    # Check V2 pool
    if config['v2_pool']:
        if check_v2_pool_exists(config['v2_pool']):
            v2_pool_contract = w3.eth.contract(address=config['v2_pool'], abi=V2_POOL_ABI)
            price_v2 = get_price_v2(v2_pool_contract, token0_decimals, token1_decimals)
            logging.info(f"V2 Price for {config['name']}: {price_v2}")
        else:
            logging.warning(f"V2 pool does not exist or is not accessible for {config['name']}")
            price_v2 = None
    else:
        logging.info(f"No V2 pool configured for {config['name']}")
        price_v2 = None
    
    # Check V3 pools
    for fee_tier, pool_info in config['v3_pools'].items():
        try:
            # Ensure the address is correctly checksummed
            pool_address = Web3.to_checksum_address(pool_info['address'])
            
            liquidity = check_v3_pool_liquidity(pool_address)
            if liquidity == 0:
                logging.warning(f"Zero liquidity in V3 pool {pool_address} for {fee_tier} fee tier")
                continue  # Skip to the next pool
            
            v3_pool_contract = w3.eth.contract(address=pool_address, abi=V3_POOL_ABI)
            price_v3 = get_price_v3(v3_pool_contract, token0_decimals, token1_decimals)
            price_v3 = validate_v3_price(price_v3, fee_tier)
            
            logging.info(f"V3 Price for {config['name']} ({fee_tier}): {price_v3}")
            
            if price_v2 is not None and price_v3 is not None:
                profit_percentage = calculate_profit_percentage(price_v2, price_v3)
                logging.info(f"Potential profit percentage: {profit_percentage}%")
                
                if is_valid_arbitrage_opportunity(price_v2, price_v3, profit_percentage):
                    logging.info(f"Valid arbitrage opportunity detected for {config['name']} ({fee_tier})")
                else:
                    logging.info(f"No valid arbitrage opportunity for {config['name']} ({fee_tier})")
        except ValueError as ve:
            logging.error(f"Invalid address for {config['name']} V3 pool ({fee_tier}): {str(ve)}")
        except Exception as e:
            logging.error(f"Error processing {config['name']} V3 pool ({fee_tier}): {str(e)}")

def main():
    for config in CONFIGURATIONS.values():
        diagnose_pair(config)
        time.sleep(1)  # Add a small delay between pairs to avoid rate limiting

if __name__ == "__main__":
    main()