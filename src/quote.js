const { ethers } = require("ethers");
const { Token, CurrencyAmount, TradeType, Percent } = require("@uniswap/sdk-core");
const { AlphaRouter } = require('@uniswap/v3-sdk');
const { Pool } = require('@uniswap/v3-sdk');

const TENDERLY_RPC_URL = "https://mainnet.gateway.tenderly.co/4XuvSWbosReD6ZCdS5naXU";
const provider = new ethers.providers.JsonRpcProvider(TENDERLY_RPC_URL);

// Uniswap contract addresses
const UNISWAP_V3_ROUTER_ADDRESS = "0xE592427A0AEce92De3Edee1F18E0157C05861564";

// Token addresses
const WETH_ADDRESS = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2";
const USDC_ADDRESS = "0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48";

// Define WETH and USDC tokens
const WETH = new Token(1, WETH_ADDRESS, 18, "WETH", "Wrapped Ether");
const USDC = new Token(1, USDC_ADDRESS, 6, "USDC", "USD Coin");

// Fetch pool data
async function getPool() {
    console.log("Fetching pool data...");
    const poolAddress = Pool.getAddress(WETH, USDC, 3000);
    const poolContract = new ethers.Contract(poolAddress, [
        "function slot0() external view returns (uint160 sqrtPriceX96, int24 tick, uint16 observationIndex, uint16 observationCardinality, uint16 observationCardinalityNext, uint8 feeProtocol, bool unlocked)"
    ], provider);

    const slot0 = await poolContract.slot0();
    console.log("Pool data fetched:", slot0);
    return new Pool(
        WETH,
        USDC,
        3000,
        slot0.sqrtPriceX96.toString(),
        1, // liquidity placeholder
        slot0.tick
    );
}

// Get quote
async function getQuote() {
    try {
        const pool = await getPool();
        console.log("Pool object created:", pool);

        const router = new AlphaRouter({ chainId: 1, provider: provider });
        console.log("AlphaRouter object created");

        const amountIn = CurrencyAmount.fromRawAmount(WETH, ethers.utils.parseEther("0.5").toString());
        console.log("Amount in:", amountIn.toSignificant(6));

        const route = await router.route(
            amountIn,
            USDC,
            TradeType.EXACT_INPUT,
            {
                recipient: "0x19F5034FAB7e2CcA2Ad46EC28acF20cbd098D3fF",
                slippageTolerance: new Percent(5, 100),
                deadline: Math.floor(Date.now() / 1000) + 60 * 20
            }
        );

        if (route) {
            console.log("Route found");
            console.log("Output amount of USDC:", route.quote.toSignificant(6));
            console.log("Price impact:", route.priceImpact.toSignificant(2), "%");
        } else {
            console.log("No route found for the trade.");
        }
    } catch (error) {
        console.error("Error fetching quote:", error);
    }
}

getQuote().catch(console.error);
