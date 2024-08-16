const hre = require("hardhat");
const ethers = hre.ethers;

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("Using account:", deployer.address);

  const tokenAddress = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"; // WETH address on mainnet
  const token = await ethers.getContractAt("IERC20", tokenAddress);
  console.log("Using token at address:", tokenAddress);

  // Deploy the BundleExecutor
  const BundleExecutor = await ethers.getContractFactory("BundleExecutor");
  const bundleExecutor = await BundleExecutor.deploy(deployer.address);
  await bundleExecutor.waitForDeployment();
  const bundleExecutorAddress = await bundleExecutor.getAddress();
  console.log("BundleExecutor deployed to:", bundleExecutorAddress);

  // Check WETH balance of BundleExecutor
  const bundleExecutorBalance = await token.balanceOf(bundleExecutorAddress);
  console.log("BundleExecutor WETH balance:", ethers.formatEther(bundleExecutorBalance));

  // Define a test bundle
  const borrowAmount = ethers.parseEther("1"); // Borrow 1 WETH
  const bundleData = {
    token: tokenAddress,
    startAmount: borrowAmount,
    endAmount: borrowAmount + ethers.parseEther("0.001"),
    callData: [
      token.interface.encodeFunctionData("transfer", [deployer.address, ethers.parseEther("0.001")])
    ],
    to: [tokenAddress]
  };

  // Encode the bundle data
  const encodedBundleData = ethers.AbiCoder.defaultAbiCoder().encode(
    ["tuple(address,uint256,uint256,bytes[],address[])"],
    [Object.values(bundleData)]
  );

  try {
    console.log("Executing test flash loan...");
    
    // Estimate gas for the transaction
    const estimatedGas = await bundleExecutor.testFlashLoan.estimateGas(
      [tokenAddress],
      [borrowAmount],
      [0n],
      encodedBundleData
    );
    console.log("Estimated gas:", estimatedGas.toString());

    const tx = await bundleExecutor.testFlashLoan(
      [tokenAddress],
      [borrowAmount],
      [0n],
      encodedBundleData,
      { gasLimit: estimatedGas * 2n } // Double the estimated gas as a precaution
    );
    
    console.log("Transaction sent. Waiting for confirmation...");
    const receipt = await tx.wait();
    console.log("Test flash loan executed. Transaction hash:", receipt.hash);

    // Log events
    for (const log of receipt.logs) {
      if (log.fragment) {
        console.log(`Event: ${log.fragment.name}`);
        console.log("Args:", log.args);
      }
    }

    // Check final balance
    const finalBalance = await token.balanceOf(bundleExecutorAddress);
    console.log("Final balance of BundleExecutor:", ethers.formatEther(finalBalance));

  } catch (error) {
    console.error("Error executing test flash loan:", error);
    if (error.transaction) {
      console.log("Failed transaction:", error.transaction);
    }
    if (error.receipt) {
      console.log("Transaction receipt:", error.receipt);
    }
  }
}

main()
  .then(() => process.exit(0))
  .catch(error => {
    console.error(error);
    process.exit(1);
  });