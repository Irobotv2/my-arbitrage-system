const { ethers } = require("hardhat");

// Addresses for mainnet
const WETH_ADDRESS = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2";
const AAVE_ADDRESS = "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9";

async function main() {
  const [signer] = await ethers.getSigners();
  console.log("Testing with account:", signer.address);

  // Replace with your deployed contract address
  const contractAddress = "0x5803367dfc46814c0085bde76500368a904d0d42";
  const FlashLoanBundleExecutor = await ethers.getContractFactory("FlashLoanBundleExecutor");
  const flashLoanExecutor = FlashLoanBundleExecutor.attach(contractAddress);

  // Get AAVE price in USD
  const aaveUsdPriceFeed = new ethers.Contract(
    "0x547a514d5e3769680Ce22B2361c10Ea13619e8a9", // AAVE/USD Chainlink price feed address
    ["function latestAnswer() view returns (int256)"],
    signer
  );
  const aavePrice = await aaveUsdPriceFeed.latestAnswer();
  console.log("AAVE price (in cents):", aavePrice.toString());

  // Calculate AAVE amount for $100 million
  const hundredMillion = ethers.parseUnits("100000000", 18);
  const oneHundredMil = BigInt(100000000) * BigInt(10**18);
  const aaveAmount = (oneHundredMil * BigInt(10**8)) / BigInt(aavePrice);

  // Test parameters
  let tokens = [WETH_ADDRESS, AAVE_ADDRESS];
  let amounts = [
    ethers.parseEther("3700"), // 3700 WETH
    aaveAmount // $100 million worth of AAVE
  ];

  // Sort tokens and amounts
  const sortedPairs = tokens.map((token, index) => ({ token, amount: amounts[index] }))
    .sort((a, b) => a.token.toLowerCase().localeCompare(b.token.toLowerCase()));

  tokens = sortedPairs.map(pair => pair.token);
  amounts = sortedPairs.map(pair => pair.amount);

  const targets = [signer.address]; // Example target
  const payloads = ["0x"];  // Empty payload

  try {
    console.log("Initiating flash loan with parameters:");
    console.log("Tokens:", tokens);
    console.log("Amounts:", amounts.map(a => a.toString()));
    console.log("Targets:", targets);
    console.log("Payloads:", payloads);

    const tx = await flashLoanExecutor.initiateFlashLoanAndBundle(
      tokens,
      amounts,
      targets,
      payloads,
      { gasLimit: 3000000n } // Increased gas limit due to larger operation
    );

    console.log("Transaction sent:", tx.hash);
    const receipt = await tx.wait();
    console.log("Transaction confirmed in block:", receipt.blockNumber);
    console.log("Gas used:", receipt.gasUsed.toString());

    if (receipt.status === 1) {
      console.log("Flash loan executed successfully!");
    } else {
      console.log("Flash loan execution failed.");
    }

    // Parse events if you've added them to your contract
    for (const log of receipt.logs) {
      try {
        const event = flashLoanExecutor.interface.parseLog(log);
        console.log("Event:", event.name, event.args);
      } catch (e) {
        // This log was from a different contract or not parseable
      }
    }
  } catch (error) {
    console.error("Error executing flash loan:", error);
    if (error.transaction) {
      console.log("Failed transaction details:", error.transaction);
    }
    if (error.receipt) {
      console.log("Transaction receipt:", error.receipt);
    }
  }
}

// Run the main function and handle any errors
main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });