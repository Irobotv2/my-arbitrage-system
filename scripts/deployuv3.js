const hre = require("hardhat");

async function main() {
  // Address of the Uniswap V3 SwapRouter
  const UNISWAP_V3_ROUTER_ADDRESS = "0xE592427A0AEce92De3Edee1F18E0157C05861564";

  console.log("Deploying UniswapV3Arbitrage contract...");

  const UniswapV3Arbitrage = await hre.ethers.getContractFactory("UniswapV3Arbitrage");
  const arbitrage = await UniswapV3Arbitrage.deploy(UNISWAP_V3_ROUTER_ADDRESS);

  await arbitrage.waitForDeployment();

  console.log("UniswapV3Arbitrage deployed to:", await arbitrage.getAddress());
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });