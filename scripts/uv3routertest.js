const hre = require("hardhat");
const { ethers } = hre;

async function main() {
  try {
    const [deployer] = await ethers.getSigners();
    console.log("Using account:", deployer.address);

    // Contract addresses
    const WETH_ADDRESS = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2";
    const USDC_ADDRESS = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48";
    const UNISWAP_V3_ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564";

    // Get contract instances
    const WETH = await ethers.getContractAt("IWETH", WETH_ADDRESS);
    const USDC = await ethers.getContractAt("@balancer-labs/v2-interfaces/contracts/solidity-utils/openzeppelin/IERC20.sol:IERC20", USDC_ADDRESS);
    const uniswapV3Router = await ethers.getContractAt("ISwapRouter", UNISWAP_V3_ROUTER);

    // Amount to swap (1 WETH)
    const amountIn = ethers.parseEther("1");

    // Wrap ETH to WETH
    await WETH.deposit({ value: amountIn });
    console.log(`Wrapped ${ethers.formatEther(amountIn)} ETH to WETH`);

    // Approve Uniswap V3 Router to spend WETH
    await WETH.approve(UNISWAP_V3_ROUTER, amountIn);
    console.log("Approved Uniswap V3 Router to spend WETH");

    // Prepare swap parameters
    const params = {
      tokenIn: WETH_ADDRESS,
      tokenOut: USDC_ADDRESS,
      fee: 3000, // 0.3% fee tier
      recipient: deployer.address,
      deadline: Math.floor(Date.now() / 1000) + 60 * 20, // 20 minutes from now
      amountIn: amountIn,
      amountOutMinimum: 0,
      sqrtPriceLimitX96: 0
    };

    // Execute swap
    console.log("Executing swap on Uniswap V3...");
    const tx = await uniswapV3Router.exactInputSingle(params);
    const receipt = await tx.wait();
    console.log("Swap executed. Transaction hash:", tx.hash);

    // Get the amount of USDC received
    const usdcBalance = await USDC.balanceOf(deployer.address);
    console.log("USDC received:", ethers.formatUnits(usdcBalance, 6));

    // Log gas used
    console.log("Gas used:", receipt.gasUsed.toString());

  } catch (error) {
    console.error("Error:", error);
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error("Error in main execution:", error);
    process.exit(1);
  });