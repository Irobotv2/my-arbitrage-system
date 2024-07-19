const hre = require("hardhat");
const { expect } = require("chai");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Using account:", deployer.address);

  const flashLoanArbitrageAddress = "0xC2EBE45652906DF9209ca97da3d7C9cc8d0D6B70";
  
  // Get the contract instance
  const FlashLoanArbitrage = await hre.ethers.getContractFactory("FlashLoanArbitrage");
  const flashLoanArbitrage = FlashLoanArbitrage.attach(flashLoanArbitrageAddress);

  console.log("FlashLoanArbitrage address:", flashLoanArbitrageAddress);

  // Test parameters
  const wethAddress = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2";
  const daiAddress = "0x6B175474E89094C44Da98b954EedeAC495271d0F";
  const usdcAddress = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48";
  const borrowAmount = hre.ethers.parseUnits("1", 18); // 1 WETH

  // Test executeArbitrage function
  async function testExecuteArbitrage() {
    console.log("Testing executeArbitrage function...");
    const tokens = [wethAddress];
    const amounts = [borrowAmount];
    const path = [wethAddress, daiAddress, usdcAddress, wethAddress];
    const pools = [
      "0xC2e9F25Be6257c210d7Adf0D4Cd6E3E881ba25f8", // WETH/DAI V3 pool
      "0x5777d92f208679DB4b9778590Fa3CAB3aC9e2168", // DAI/USDC V3 pool
      "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"  // USDC/WETH V3 pool
    ];
    const isV3 = [true, true, true];
    const fees = [3000, 100, 500]; // 0.3%, 0.01%, 0.05% fees

    try {
      const tx = await flashLoanArbitrage.executeArbitrage(tokens, amounts, path, pools, isV3, fees, { gasLimit: 5000000 });
      console.log("Arbitrage transaction sent:", tx.hash);
      const receipt = await tx.wait();
      console.log("Arbitrage transaction confirmed in block:", receipt.blockNumber);
      console.log("Arbitrage executed successfully");
    } catch (error) {
      console.error("Error executing arbitrage:", error);
    }
  }

  // Test withdraw function
  async function testWithdraw() {
    console.log("Testing withdraw function...");
    const withdrawAmount = hre.ethers.parseUnits("0.1", 18); // 0.1 ETH
    try {
      const tx = await flashLoanArbitrage.withdraw(hre.ethers.ZeroAddress, withdrawAmount);
      console.log("Withdraw transaction sent:", tx.hash);
      const receipt = await tx.wait();
      console.log("Withdraw transaction confirmed in block:", receipt.blockNumber);
      console.log("Withdraw executed successfully");
    } catch (error) {
      console.error("Error executing withdraw:", error);
    }
  }

  // Run tests
  await testExecuteArbitrage();
  await testWithdraw();
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });