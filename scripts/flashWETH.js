const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Using account:", deployer.address);

  // Address of the deployed FlashLoanRecipient contract
  const flashLoanRecipientAddress = "0xD71F03bC9C99B7437002102BA44E77f82755A6DD";
  
  // Get the contract instance
  const FlashLoanRecipient = await hre.ethers.getContractFactory("FlashLoanRecipient");
  const flashLoanRecipient = FlashLoanRecipient.attach(flashLoanRecipientAddress);

  console.log("FlashLoanRecipient address:", flashLoanRecipientAddress);

  const balancerVaultAddress = "0xBA12222222228d8Ba445958a75a0704d566BF2C8";
  const wethAddress = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2";

  // 3700 WETH
  const borrowAmount = hre.ethers.parseUnits("3700", 18);

  const tokens = [wethAddress];
  const amounts = [borrowAmount];
  const userData = "0x"; // This can be left as an empty bytes string

  try {
    console.log("Attempting to execute flash loan for 3700 WETH...");
    const tx = await flashLoanRecipient.makeFlashLoan(
      tokens,
      amounts,
      userData,
      { gasLimit: 5000000 } // Increased gas limit for larger loan
    );
    console.log("Flash loan transaction sent:", tx.hash);
    const receipt = await tx.wait();
    console.log("Flash loan transaction confirmed in block:", receipt.blockNumber);
    console.log("Flash loan executed successfully");
  } catch (error) {
    console.error("Error executing flash loan:", error);
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