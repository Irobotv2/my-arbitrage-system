const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Using account:", deployer.address);

  // Address of the deployed FlashLoanRecipient contract
  const flashLoanRecipientAddress = "0xF436C1f83f6e8722054e981837fa0b9a810F9DD1";
  
  // Get the contract instance
  const FlashLoanRecipient = await hre.ethers.getContractFactory("FlashLoanRecipient");
  const flashLoanRecipient = FlashLoanRecipient.attach(flashLoanRecipientAddress);

  console.log("FlashLoanRecipient address:", flashLoanRecipientAddress);

  const balancerVaultAddress = "0xBA12222222228d8Ba445958a75a0704d566BF2C8";
  const daiAddress = "0x6B175474E89094C44Da98b954EedeAC495271d0F";

  // 1.7 million DAI
  const borrowAmount = hre.ethers.parseUnits("1700000", 18);

  const tokens = [daiAddress];
  const amounts = [borrowAmount];
  const userData = "0x"; // This can be left as an empty bytes string

  try {
    console.log("Attempting to execute flash loan for 1.7 million DAI...");
    const tx = await flashLoanRecipient.makeFlashLoan(
      tokens,
      amounts,
      userData,
      { gasLimit: 3000000 } // Increased gas limit for larger loan
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