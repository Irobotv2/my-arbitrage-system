const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Using account:", deployer.address);

  // Address of the deployed FlashLoanArbitrage contract
  const flashLoanArbitrageAddress = "0xC2EBE45652906DF9209ca97da3d7C9cc8d0D6B70";
  
  // Get the contract instance
  const FlashLoanArbitrage = await hre.ethers.getContractFactory("FlashLoanArbitrage");
  const flashLoanArbitrage = FlashLoanArbitrage.attach(flashLoanArbitrageAddress);

  console.log("FlashLoanArbitrage address:", flashLoanArbitrageAddress);

  const wethAddress = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2";

  // 3700 WETH
  const borrowAmount = hre.ethers.parseUnits("3700", 18);

  const tokens = [wethAddress];
  const amounts = [borrowAmount];
  
  // Default path for WETH arbitrage (you may want to make this configurable)
  const path = [wethAddress, wethAddress];
  const pools = ["0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"]; // WETH/USDC V3 pool
  const isV3 = [true];
  const fees = [3000]; // 0.3% fee tier

  try {
    console.log("Attempting to execute flash loan arbitrage for 3700 WETH...");
    const tx = await flashLoanArbitrage.executeArbitrage(
      tokens,
      amounts,
      path,
      pools,
      isV3,
      fees,
      { gasLimit: 5000000 } // Increased gas limit for larger loan
    );
    console.log("Flash loan arbitrage transaction sent:", tx.hash);
    const receipt = await tx.wait();
    console.log("Flash loan arbitrage transaction confirmed in block:", receipt.blockNumber);
    console.log("Flash loan arbitrage executed successfully");
  } catch (error) {
    console.error("Error executing flash loan arbitrage:", error);
    if (error.reason) {
      console.error("Error reason:", error.reason);
    }
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });