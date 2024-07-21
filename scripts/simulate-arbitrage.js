const { ethers } = require("ethers");
const fs = require('fs');
const axios = require('axios');
const mysql = require('mysql2/promise');

// ABI for FlashLoanArbitrage contract
const YOUR_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {
                        "internalType": "address",
                        "name": "tokenIn",
                        "type": "address"
                    },
                    {
                        "internalType": "address",
                        "name": "tokenOut",
                        "type": "address"
                    },
                    {
                        "internalType": "address",
                        "name": "pool",
                        "type": "address"
                    },
                    {
                        "internalType": "bool",
                        "name": "isV3",
                        "type": "bool"
                    },
                    {
                        "internalType": "uint24",
                        "name": "fee",
                        "type": "uint24"
                    }
                ],
                "internalType": "struct FlashLoanArbitrage.SwapStep[]",
                "name": "path",
                "type": "tuple[]"
            },
            {
                "internalType": "uint256",
                "name": "flashLoanAmount",
                "type": "uint256"
            }
        ],
        "name": "executeArbitrage",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    // Include other functions if necessary
];

// Configuration
const CONFIG = {
    FLASH_LOAN_ARBITRAGE_ADDRESS: "0x48334a214155101522519c5f6c2d82e46cb405d4",
    API_KEY: "bde86d5008a99eaf066b94e4cfcad7fc",
    UNISWAP_V2_URL: `https://gateway-arbitrum.network.thegraph.com/api/{API_KEY}/subgraphs/id/2ZXJn1QPvBpS1UVAsSMvqeGm3XvN29GVo75pXafmiNFb`,
    UNISWAP_V3_URL: `https://gateway-arbitrum.network.thegraph.com/api/{API_KEY}/subgraphs/id/Dki5NV9qnFsg6cLpUH8rHMuNz1tskkgKw94ercyuo1ws`,
    INITIAL_FLASH_LOAN_AMOUNT: ethers.parseEther("10"),
    DURATION_HOURS: 1,
    INTERVAL_MINUTES: 5,
    MAX_PATH_LENGTH: 5,
    MYSQL: {
        host: 'localhost',
        user: 'arbitrage_user',
        password: 'Newpassword1!',
        database: 'arbitrage_system'
    }
};

const MIN_LIQUIDITY_THRESHOLD = 10000; // $10,000 USD equivalent

const YOUR_RPC_URL = "https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c";

// Helper functions
function bigIntToString(obj) {
    return JSON.parse(JSON.stringify(obj, (key, value) =>
        typeof value === 'bigint' ? value.toString() : value
    ));
}

async function fetchPoolData(url, query) {
    try {
        const response = await axios.post(url, { query });
        return response.data?.data || null;
    } catch (error) {
        console.error(`Error fetching pool data from ${url}:`, error.message);
        return null;
    }
}

// Main functions
async function getPoolData() {
    const v2Query = `{
      pairs(first: 1000, orderBy: reserveUSD, orderDirection: desc) {
        id
        token0 { id symbol }
        token1 { id symbol }
        reserve0
        reserve1
        reserveUSD
      }
    }`;

    const v3Query = `{
      pools(first: 1000, orderBy: totalValueLockedUSD, orderDirection: desc) {
        id
        token0 { id symbol }
        token1 { id symbol }
        sqrtPrice
        liquidity
        feeTier
      }
    }`;

    const [v2Data, v3Data] = await Promise.all([
        fetchPoolData(CONFIG.UNISWAP_V2_URL.replace('{API_KEY}', CONFIG.API_KEY), v2Query),
        fetchPoolData(CONFIG.UNISWAP_V3_URL.replace('{API_KEY}', CONFIG.API_KEY), v3Query)
    ]);

    return { 
        v2Pools: v2Data?.pairs || [], 
        v3Pools: v3Data?.pools || [] 
    };
}

function calculatePoolPrice(pool) {
    const { reserve0, reserve1, sqrtPrice } = pool;
    if (reserve0 && reserve1) {
        const reserve0Big = BigInt(ethers.parseUnits(reserve0, 18));
        const reserve1Big = BigInt(ethers.parseUnits(reserve1, 18));
        return reserve0Big !== BigInt(0) ? reserve1Big * BigInt(1e18) / reserve0Big : BigInt(0);
    } else if (sqrtPrice) {
        return (BigInt(sqrtPrice) * BigInt(sqrtPrice) * BigInt(1e18)) / (BigInt(2) ** BigInt(192));
    }
    return BigInt(1e18); // Default to 1:1 if we can't calculate
}

function calculateLiquidityScore(pool) {
    if (pool.reserveUSD) {
        return parseFloat(pool.reserveUSD);
    } else if (pool.liquidity) {
        return parseFloat(pool.liquidity);
    }
    return 0;
}

function buildTokenGraph(pools) {
    const tokenGraph = {};
    let excludedPools = 0;
    pools.forEach(pool => {
        const liquidityScore = calculateLiquidityScore(pool);
        if (liquidityScore < MIN_LIQUIDITY_THRESHOLD) {
            excludedPools++;
            return;
        }
        const { token0, token1, id, feeTier } = pool;
        if (!tokenGraph[token0.id]) tokenGraph[token0.id] = {};
        if (!tokenGraph[token1.id]) tokenGraph[token1.id] = {};

        const price = calculatePoolPrice(pool);

        tokenGraph[token0.id][token1.id] = { pool: id, feeTier, price: price.toString(), liquidity: liquidityScore };
        tokenGraph[token1.id][token0.id] = { 
            pool: id, 
            feeTier, 
            price: price !== BigInt(0) ? (BigInt(1e36) / price).toString() : "0",
            liquidity: liquidityScore
        };
    });
    console.log(`Excluded ${excludedPools} pools due to low liquidity`);
    return tokenGraph;
}

function generateArbitragePaths(pools, maxPathLength = CONFIG.MAX_PATH_LENGTH) {
    console.log(`Starting path generation with ${pools.length} pools...`);
    const tokenGraph = buildTokenGraph(pools);
    console.log(`Built token graph with ${Object.keys(tokenGraph).length} tokens`);
    const paths = [];
    let pathsGenerated = 0;

    function dfs(currentPath, visited) {
        if (currentPath.length > 1 && currentPath[0] === currentPath[currentPath.length - 1]) {
            paths.push(currentPath.map((token, index) => formatPathStep(token, index, currentPath, tokenGraph)));
            pathsGenerated++;
            if (pathsGenerated % 1000 === 0) {
                console.log(`Generated ${pathsGenerated} paths so far...`);
            }
            return;
        }

        if (currentPath.length >= maxPathLength) return;

        const currentToken = currentPath[currentPath.length - 1];
        for (const nextToken in tokenGraph[currentToken]) {
            if (!visited.has(nextToken) || nextToken === currentPath[0]) {
                dfs([...currentPath, nextToken], new Set([...visited, nextToken]));
            }
        }
    }

    for (const startToken in tokenGraph) {
        dfs([startToken], new Set([startToken]));
    }

    console.log(`Path generation complete. Total paths: ${paths.length}`);
    return paths;
}

function formatPathStep(token, index, path, tokenGraph) {
    if (index === path.length - 1) return null;
    const nextToken = path[index + 1];
    return {
        tokenIn: token,
        tokenOut: nextToken,
        pool: tokenGraph[token][nextToken].pool,
        isV3: !!tokenGraph[token][nextToken].feeTier,
        fee: tokenGraph[token][nextToken].feeTier || 0,
        price: tokenGraph[token][nextToken].price,
        liquidity: tokenGraph[token][nextToken].liquidity
    };
}

function filterPotentiallyProfitablePaths(paths) {
    const filteredPaths = paths.filter(path => {
        let cumulativePrice = 1;
        for (const step of path) {
            if (step === null) continue;
            cumulativePrice *= parseFloat(step.price);
        }
        // If the cumulative price is greater than 1, it might be profitable
        return cumulativePrice > 1.001; // 0.1% potential profit threshold
    });
    console.log(`Filtered ${paths.length - filteredPaths.length} potentially unprofitable paths`);
    return filteredPaths;
}

async function simulateArbitragePath(flashLoanAmount, path) {
    const provider = new ethers.JsonRpcProvider(YOUR_RPC_URL);
    const signer = provider.getSigner();
    const flashLoanArbitrage = new ethers.Contract(CONFIG.FLASH_LOAN_ARBITRAGE_ADDRESS, YOUR_ABI, signer);

    try {
        // Filter out null steps and format the path
        const formattedPath = path.filter(step => step !== null).map(step => ({
            tokenIn: step.tokenIn,
            tokenOut: step.tokenOut,
            pool: step.pool,
            isV3: step.isV3,
            fee: step.fee
        }));

        console.log("Detailed Path Information:");
        formattedPath.forEach((step, index) => {
            console.log(`Step ${index + 1}:`);
            console.log(`  Token In: ${step.tokenIn}`);
            console.log(`  Token Out: ${step.tokenOut}`);
            console.log(`  Pool: ${step.pool}`);
            console.log(`  Is V3: ${step.isV3}`);
            console.log(`  Fee: ${step.fee}`);
        });

        console.log("Attempting to simulate arbitrage with formatted path...");
        const [estimatedProfit, simulationResults] = await flashLoanArbitrage.simulateArbitrage(formattedPath, flashLoanAmount);
        
        const tokenSequence = formattedPath.map(step => `${step.tokenIn} -> ${step.tokenOut}`).join(' -> ');
        const profitInEth = ethers.formatEther(estimatedProfit);
        const profitPercentage = (parseFloat(profitInEth) / parseFloat(ethers.formatEther(flashLoanAmount)) * 100).toFixed(2);

        const logEntry = {
            timestamp: new Date().toISOString(),
            tokenSequence,
            path: bigIntToString(formattedPath),
            estimatedProfit: profitInEth,
            profitPercentage: `${profitPercentage}%`,
            flashLoanAmount: ethers.formatEther(flashLoanAmount),
            simulationResults: simulationResults.map(r => ethers.formatEther(r))
        };

        console.log("Arbitrage Opportunity:");
        console.log(`Token Sequence: ${tokenSequence}`);
        console.log(`Estimated Profit: ${profitInEth} ETH (${profitPercentage}%)`);
        console.log(`Flash Loan Amount: ${ethers.formatEther(flashLoanAmount)} ETH`);
        console.log(`Simulation Results: ${logEntry.simulationResults.join(' -> ')}`);
        console.log("--------------------");

        fs.appendFileSync('arbitrage_opportunities.log', JSON.stringify(logEntry) + '\n');

        if (estimatedProfit > 0n) {
            fs.appendFileSync('profitable_opportunities.log', JSON.stringify(logEntry) + '\n');
            await cacheProfitableOpportunity(logEntry);
        }

        return { isProfitable: estimatedProfit > 0n, profit: estimatedProfit, logEntry };
    } catch (error) {
        console.error("Error during simulation:", error);
        console.error("Path causing error:", JSON.stringify(path, null, 2));
        return { isProfitable: false, profit: 0n, logEntry: null };
    }
}

async function cacheProfitableOpportunity(opportunity) {
    const connection = await mysql.createConnection(CONFIG.MYSQL);
    try {
        await connection.execute(
            'INSERT INTO profitable_opportunities (timestamp, token_sequence, estimated_profit, profit_percentage, flash_loan_amount, path_json) VALUES (?, ?, ?, ?, ?, ?)',
            [
                opportunity.timestamp,
                opportunity.tokenSequence,
                opportunity.estimatedProfit,
                opportunity.profitPercentage,
                opportunity.flashLoanAmount,
                JSON.stringify(opportunity.path)
            ]
        );
    } catch (error) {
        console.error("Error caching profitable opportunity:", error);
    } finally {
        await connection.end();
    }
}

async function executeArbitragePath(flashLoanAmount) {
    const provider = new ethers.JsonRpcProvider(YOUR_RPC_URL);
    const signer = provider.getSigner();
    const flashLoanArbitrage = new ethers.Contract(CONFIG.FLASH_LOAN_ARBITRAGE_ADDRESS, YOUR_ABI, signer);

    // Define a single path for testing
    const singlePath = [
        {
            tokenIn: "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", // USDC
            tokenOut: "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", // WETH
            pool: "0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8",
            isV3: true,
            fee: 3000
        },
        {
            tokenIn: "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", // WETH
            tokenOut: "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", // USDC
            pool: "0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8",
            isV3: true,
            fee: 3000
        }
    ];

    try {
        console.log("Detailed Path Information:");
        singlePath.forEach((step, index) => {
            console.log(`Step ${index + 1}:`);
            console.log(`  Token In: ${step.tokenIn}`);
            console.log(`  Token Out: ${step.tokenOut}`);
            console.log(`  Pool: ${step.pool}`);
            console.log(`  Is V3: ${step.isV3}`);
            console.log(`  Fee: ${step.fee}`);
        });

        console.log("Attempting to execute arbitrage with single path...");
        const tx = await flashLoanArbitrage.executeArbitrage(singlePath, flashLoanAmount, { gasLimit: 5000000 });
        console.log("Transaction sent:", tx.hash);
        const receipt = await tx.wait();
        console.log("Transaction confirmed in block:", receipt.blockNumber);

        console.log("Arbitrage executed successfully");
        return { success: true, txHash: tx.hash };
    } catch (error) {
        console.error("Error during arbitrage execution:", error);
        return { success: false, error: error.message };
    }
}

// Usage
async function main() {
    const flashLoanAmount = ethers.parseEther("10"); // 10 ETH for example
    const result = await executeArbitragePath(flashLoanAmount);
    console.log("Execution result:", result);
}

main()
    .then(() => process.exit(0))
    .catch(error => {
        console.error(error);
        process.exit(1);
    });
