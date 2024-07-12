from web3 import Web3
from web3.middleware import geth_poa_middleware

# Configuration
TENDERLY_URL = "https://virtual.mainnet.rpc.tenderly.co/c4e60e60-6398-4e23-9ffc-f48f66d9706e"
web3 = Web3(Web3.HTTPProvider(TENDERLY_URL))
web3.middleware_onion.inject(geth_poa_middleware, layer=0)

# Uniswap V2 Router address
uniswap_v2_router = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"

# Token addresses
usdc_address = web3.to_checksum_address("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606EB48")
weth_address = web3.to_checksum_address("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")

# Uniswap V2 Router ABI (only the function we need)
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
    }
]

# Create contract object
router_contract = web3.eth.contract(address=uniswap_v2_router, abi=router_abi)

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

def calculate_weth_to_usdc_v2(usd_amount):
    weth_price = get_weth_price_in_usd_v2()
    if weth_price:
        weth_amount = (usd_amount / weth_price) * 1e18  # Convert to WETH's 18 decimals
        try:
            amounts_out = router_contract.functions.getAmountsOut(
                int(weth_amount),
                [weth_address, usdc_address]
            ).call()
            usdc_out = amounts_out[1] / 1e6  # Convert from USDC's 6 decimals
            print(f"${usd_amount} worth of WETH ({weth_amount / 1e18:.6f} WETH) can be exchanged for {usdc_out:.2f} USDC on Uniswap V2")
            print(f"Uniswap V2 fee: 0.3%")
        except Exception as e:
            print(f"Error getting quote for WETH to USDC: {e}")
    else:
        print("Failed to calculate due to missing WETH price")

# Run the calculation
calculate_weth_to_usdc_v2(1000)