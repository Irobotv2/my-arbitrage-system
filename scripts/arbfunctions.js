const hre = require("hardhat");
const { ethers } = hre;

async function main() {
  // Use your existing arbitrage contract
  const arbitrageAddress = "0x16c2560bb2821e56a20c073963e9908298f68200";
  console.log("Arbitrage address:", arbitrageAddress);

  try {
    const FlashLoanArbitrage = await ethers.getContractFactory("FlashLoanArbitrage");
    const arbitrage = FlashLoanArbitrage.attach(arbitrageAddress);

    if (!arbitrage.address) {
      throw new Error("Failed to connect to the contract at " + arbitrageAddress);
    }
    console.log("Successfully connected to contract at:", arbitrage.address);

    // Define token addresses
    const WETH_ADDRESS = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2";
    const USDC_ADDRESS = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48";

    // Amount to swap (e.g., 1 WETH)
    const amountIn = ethers.parseEther("1");

    // Get WETH contract
    const WETH = await ethers.getContractAt("IWETH", WETH_ADDRESS);

    // Get a signer
    const [signer] = await ethers.getSigners();

    // Wrap some ETH to WETH
    console.log("Wrapping ETH to WETH...");
    await WETH.connect(signer).deposit({ value: amountIn });
    console.log("ETH wrapped successfully");

    // Approve arbitrage contract to spend WETH
    console.log("Approving WETH spend...");
    await WETH.connect(signer).approve(arbitrage.address, amountIn);
    console.log("WETH spend approved");

    // Function to execute and log swap
    async function executeAndLogSwap(description, swapFunction) {
      console.log(`Executing ${description}...`);
      const tx = await swapFunction();
      const receipt = await tx.wait();
      console.log(`${description} successful. Gas used:`, receipt.gasUsed.toString());
      return receipt;
    }

    // Swap WETH to USDC on Uniswap V2
    const uniswapV2Receipt = await executeAndLogSwap("WETH to USDC on Uniswap V2", () => 
      arbitrage.swapOnUniswapV2(WETH_ADDRESS, USDC_ADDRESS, amountIn, 0)
    );

    // Get USDC balance after first swap
    const usdcBalance = await arbitrage.getTokenBalance(USDC_ADDRESS);
    console.log("USDC balance after first swap:", ethers.formatUnits(usdcBalance, 6));  // USDC has 6 decimals

    // Swap USDC back to WETH on Uniswap V3
    const uniswapV3Receipt = await executeAndLogSwap("USDC to WETH on Uniswap V3", () => 
      arbitrage.swapOnUniswapV3(USDC_ADDRESS, WETH_ADDRESS, usdcBalance, 0)
    );

    // Check if both swaps were in the same block
    if (uniswapV2Receipt.blockNumber === uniswapV3Receipt.blockNumber) {
      console.log("Both swaps executed in the same block:", uniswapV2Receipt.blockNumber);
    } else {
      console.log("Swaps executed in different blocks:");
      console.log("Uniswap V2 block:", uniswapV2Receipt.blockNumber);
      console.log("Uniswap V3 block:", uniswapV3Receipt.blockNumber);
    }

    // Get final WETH balance
    const finalWethBalance = await arbitrage.getTokenBalance(WETH_ADDRESS);
    console.log("Final WETH balance:", ethers.formatUnits(finalWethBalance, 18));

  } catch (error) {
    console.error("Error during execution:", error);
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error("Error in main execution:", error);
    process.exit(1);
  });