const hre = require("hardhat");

async function main() {
  // Address of Uniswap V2 Router
  const UNISWAP_V2_ROUTER = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D";
  
  // Address of Uniswap V3 SwapRouter
  const UNISWAP_V3_ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564";

  console.log("Deploying UniswapV2V3FlashArbitrage...");

  const UniswapV2V3FlashArbitrage = await hre.ethers.getContractFactory("UniswapV2V3FlashArbitrage");
  const arbitrage = await UniswapV2V3FlashArbitrage.deploy(UNISWAP_V2_ROUTER, UNISWAP_V3_ROUTER);

  await arbitrage.waitForDeployment();

  console.log("UniswapV2V3FlashArbitrage deployed to:", await arbitrage.getAddress());
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });