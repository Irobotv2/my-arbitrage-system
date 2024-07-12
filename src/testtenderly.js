import { ethers } from "ethers";
import { Mnemonic, Wallet } from "ethers";

// Configuration
const RPC_URL = "https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c";
const EXPLORER_BASE_URL = "https://dashboard.tenderly.co/explorer/300a688c-e670-4eaa-a8d0-e55dc49b649c";

// Set up the provider and signer
const provider = new ethers.JsonRpcProvider(RPC_URL);
const mnemonic = Mnemonic.fromEntropy(ethers.utils.randomBytes(24));
const signer = Wallet.fromPhrase(mnemonic.phrase, provider);

// Main function to test the configuration
(async () => {
  try {
    // Set the balance of the signer's address
    await provider.send("tenderly_setBalance", [
      signer.address,
      "0xDE0B6B3A7640000", // 1 ETH in Wei
    ]);
    console.log(`Balance set for address ${signer.address}`);

    // Send a transaction
    const tx = await signer.sendTransaction({
      to: "0xa5cc3c03994DB5b0d9A5eEdD10CabaB0813678AC",
      value: ethers.utils.parseEther("0.01"),
    });

    console.log(`Transaction sent: ${tx.hash}`);
    console.log(`${EXPLORER_BASE_URL}/tx/${tx.hash}`);
  } catch (e) {
    console.error(e);
    process.exitCode = 1;
  }
})();
