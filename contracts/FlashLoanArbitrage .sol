// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.7.0;
pragma abicoder v2;

import {IVault} from "@balancer-labs/v2-interfaces/contracts/vault/IVault.sol";
import {IFlashLoanRecipient} from "@balancer-labs/v2-interfaces/contracts/vault/IFlashLoanRecipient.sol";
import {IERC20} from "@balancer-labs/v2-interfaces/contracts/solidity-utils/openzeppelin/IERC20.sol";
import "@uniswap/v2-periphery/contracts/interfaces/IUniswapV2Router02.sol";
import "@uniswap/v3-periphery/contracts/interfaces/ISwapRouter.sol";
import "@uniswap/v2-core/contracts/interfaces/IUniswapV2Pair.sol";

contract FlashLoanArbitrage is IFlashLoanRecipient {
    IVault private constant BALANCER_VAULT = IVault(0xBA12222222228d8Ba445958a75a0704d566BF2C8);
    IUniswapV2Router02 private constant UNISWAP_V2_ROUTER = IUniswapV2Router02(0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D);
    ISwapRouter private constant UNISWAP_V3_ROUTER = ISwapRouter(0xE592427A0AEce92De3Edee1F18E0157C05861564);
    address public owner;

    event FlashLoanInitiated(address[] tokens, uint256[] amounts);
    event FlashLoanCompleted(address[] tokens, uint256[] amounts, uint256[] fees);
    event BalanceCheck(address token, uint256 balance);
    event ArbitrageExecuted(uint256 profit);

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can call this function");
        _;
    }

    function executeArbitrage(
        IERC20[] memory tokens,
        uint256[] memory amounts,
        address[] memory path,
        address[] memory pools,
        bool[] memory isV3,
        uint24[] memory fees
    ) external onlyOwner {
        require(tokens.length == 1, "Only single token flash loans supported");
        BALANCER_VAULT.flashLoan(this, tokens, amounts, abi.encode(path, pools, isV3, fees));
    }

    function receiveFlashLoan(
        IERC20[] memory tokens,
        uint256[] memory amounts,
        uint256[] memory feeAmounts,
        bytes memory userData
    ) external override {
        require(msg.sender == address(BALANCER_VAULT), "Only Balancer Vault can call this function");
        
        (address[] memory path, address[] memory pools, bool[] memory isV3, uint24[] memory fees) = abi.decode(userData, (address[], address[], bool[], uint24[]));
        uint256 flashLoanAmount = amounts[0];
        uint256 flashLoanFee = feeAmounts[0];

        // Log the received amounts
        for (uint256 i = 0; i < tokens.length; i++) {
            uint256 balance = tokens[i].balanceOf(address(this));
            emit BalanceCheck(address(tokens[i]), balance);
        }

        // Execute arbitrage
        uint256 startBalance = IERC20(path[0]).balanceOf(address(this));
        
        for (uint i = 0; i < path.length - 1; i++) {
            uint256 amountIn = i == 0 ? flashLoanAmount : IERC20(path[i]).balanceOf(address(this));
            if (isV3[i]) {
                executeV3Swap(path[i], path[i+1], pools[i], amountIn, fees[i]);
            } else {
                executeV2Swap(path[i], path[i+1], pools[i], amountIn);
            }
        }

        uint256 endBalance = IERC20(path[0]).balanceOf(address(this));
        require(endBalance >= startBalance + flashLoanFee, "Arbitrage didn't profit");

        // Repay flash loan
        IERC20(path[0]).transfer(address(BALANCER_VAULT), flashLoanAmount + flashLoanFee);

        // Calculate and emit profit
        uint256 profit = endBalance - (startBalance + flashLoanFee);
        emit ArbitrageExecuted(profit);

        address[] memory tokenAddresses = new address[](tokens.length);
        for (uint i = 0; i < tokens.length; i++) {
            tokenAddresses[i] = address(tokens[i]);
        }
        emit FlashLoanCompleted(tokenAddresses, amounts, feeAmounts);
    }

    function executeV2Swap(address tokenIn, address tokenOut, address pool, uint256 amountIn) internal {
        IERC20(tokenIn).transfer(pool, amountIn);
        (uint amount0Out, uint amount1Out) = IUniswapV2Pair(pool).token0() == tokenOut 
            ? (IERC20(tokenOut).balanceOf(address(this)), uint(0)) 
            : (uint(0), IERC20(tokenOut).balanceOf(address(this)));
        IUniswapV2Pair(pool).swap(amount0Out, amount1Out, address(this), new bytes(0));
    }

    function executeV3Swap(address tokenIn, address tokenOut, address pool, uint256 amountIn, uint24 fee) internal {
        IERC20(tokenIn).approve(address(UNISWAP_V3_ROUTER), amountIn);
        ISwapRouter.ExactInputSingleParams memory params = ISwapRouter.ExactInputSingleParams({
            tokenIn: tokenIn,
            tokenOut: tokenOut,
            fee: fee,
            recipient: address(this),
            deadline: block.timestamp,
            amountIn: amountIn,
            amountOutMinimum: 0,
            sqrtPriceLimitX96: 0
        });
        UNISWAP_V3_ROUTER.exactInputSingle(params);
    }

    // Allow contract to receive ETH
    receive() external payable {}

    // Function to withdraw any tokens or ETH stuck in the contract
    function withdraw(address token, uint256 amount) external onlyOwner {
        if (token == address(0)) {
            payable(owner).transfer(amount);
        } else {
            IERC20(token).transfer(owner, amount);
        }
    }
}