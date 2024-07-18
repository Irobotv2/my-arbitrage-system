// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.7.0;
pragma abicoder v2;

import {IVault} from "@balancer-labs/v2-interfaces/contracts/vault/IVault.sol";
import {IFlashLoanRecipient} from "@balancer-labs/v2-interfaces/contracts/vault/IFlashLoanRecipient.sol";
import {IERC20} from "@balancer-labs/v2-interfaces/contracts/solidity-utils/openzeppelin/IERC20.sol";
import "@uniswap/v2-periphery/contracts/interfaces/IUniswapV2Router02.sol";
import "@uniswap/v3-periphery/contracts/interfaces/ISwapRouter.sol";

contract DynamicFlashLoanArbitrage is IFlashLoanRecipient {
    IVault private constant BALANCER_VAULT = IVault(0xBA12222222228d8Ba445958a75a0704d566BF2C8);
    IUniswapV2Router02 private immutable uniswapV2Router;
    ISwapRouter private immutable uniswapV3Router;
    address public owner;

    struct ArbitrageParameters {
        address tokenIn;
        address tokenOut;
        uint256 amount;
        uint256 minOutV2;
        uint256 minOutV3;
        uint24 v3Fee;
    }

    event FlashLoanInitiated(address[] tokens, uint256[] amounts);
    event FlashLoanCompleted(address[] tokens, uint256[] amounts, uint256[] fees);
    event BalanceCheck(address token, uint256 balance);
    event ArbitrageExecuted(address tokenIn, address tokenOut, uint256 amountIn, uint256 amountOut, uint256 profit);
    event ErrorOccurred(string step, string reason);
    event SwapAmounts(string step, uint256 amountIn, uint256 amountOut);

    constructor(address _uniswapV2Router, address _uniswapV3Router) {
        uniswapV2Router = IUniswapV2Router02(_uniswapV2Router);
        uniswapV3Router = ISwapRouter(_uniswapV3Router);
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can call this function");
        _;
    }

    function initiateArbitrage(
        IERC20[] memory tokens,
        uint256[] memory amounts,
        ArbitrageParameters memory params
    ) external onlyOwner {
        bytes memory userData = abi.encode(params);
        emit FlashLoanInitiated(getAddresses(tokens), amounts);
        try BALANCER_VAULT.flashLoan(this, tokens, amounts, userData) {
            // Flash loan initiated successfully
        } catch Error(string memory reason) {
            emit ErrorOccurred("Initiating flash loan", reason);
            revert(string(abi.encodePacked("Flash loan initiation failed: ", reason)));
        }
    }

    function receiveFlashLoan(
        IERC20[] memory tokens,
        uint256[] memory amounts,
        uint256[] memory feeAmounts,
        bytes memory userData
    ) external override {
        require(msg.sender == address(BALANCER_VAULT), "Only Balancer Vault can call this function");

        ArbitrageParameters memory params = abi.decode(userData, (ArbitrageParameters));

        for (uint256 i = 0; i < tokens.length; i++) {
            emit BalanceCheck(address(tokens[i]), tokens[i].balanceOf(address(this)));
        }

        try this.executeArbitrage(params, feeAmounts[0]) {
            // Arbitrage executed successfully
        } catch Error(string memory reason) {
            emit ErrorOccurred("Executing arbitrage", reason);
            revert(string(abi.encodePacked("Arbitrage execution failed: ", reason)));
        }

        emit FlashLoanCompleted(getAddresses(tokens), amounts, feeAmounts);
    }

    function executeArbitrage(
        ArbitrageParameters memory params,
        uint256 feeAmount
    ) external {
        require(msg.sender == address(this), "Only callable internally");

        emit BalanceCheck(params.tokenIn, IERC20(params.tokenIn).balanceOf(address(this)));
        emit BalanceCheck(params.tokenOut, IERC20(params.tokenOut).balanceOf(address(this)));

        // Approve and trade on Uniswap V2
        IERC20(params.tokenIn).approve(address(uniswapV2Router), params.amount);
        address[] memory path = new address[](2);
        path[0] = params.tokenIn;
        path[1] = params.tokenOut;

        uint256 amountOutV2;
        try uniswapV2Router.getAmountsOut(params.amount, path) returns (uint256[] memory amountsOut) {
            amountOutV2 = amountsOut[1];
            emit SwapAmounts("Uniswap V2 Expected", params.amount, amountOutV2);
        } catch {
            emit ErrorOccurred("Uniswap V2", "Failed to get amounts out");
            revert("Failed to get amounts from Uniswap V2");
        }

        if (amountOutV2 < params.minOutV2) {
            emit ErrorOccurred("Uniswap V2", "Insufficient output amount");
            revert("UniswapV2Router: INSUFFICIENT_OUTPUT_AMOUNT");
        }

        try uniswapV2Router.swapExactTokensForTokens(
            params.amount,
            params.minOutV2,
            path,
            address(this),
            block.timestamp
        ) returns (uint256[] memory amounts) {
            amountOutV2 = amounts[1];
            emit SwapAmounts("Uniswap V2 Actual", params.amount, amountOutV2);
        } catch {
            emit ErrorOccurred("Uniswap V2", "Swap failed");
            revert("Swap on Uniswap V2 failed");
        }

        emit ArbitrageExecuted(params.tokenIn, params.tokenOut, params.amount, amountOutV2, 0);

        // Approve and trade on Uniswap V3
        IERC20(params.tokenOut).approve(address(uniswapV3Router), amountOutV2);
        ISwapRouter.ExactInputSingleParams memory v3Params = ISwapRouter.ExactInputSingleParams({
            tokenIn: params.tokenOut,
            tokenOut: params.tokenIn,
            fee: params.v3Fee,
            recipient: address(this),
            deadline: block.timestamp,
            amountIn: amountOutV2,
            amountOutMinimum: params.minOutV3,
            sqrtPriceLimitX96: 0
        });

        uint256 amountOutV3;
        try uniswapV3Router.exactInputSingle(v3Params) returns (uint256 amountOut) {
            amountOutV3 = amountOut;
            emit SwapAmounts("Uniswap V3 Actual", amountOutV2, amountOutV3);
        } catch {
            emit ErrorOccurred("Uniswap V3", "Swap failed");
            revert("Swap on Uniswap V3 failed");
        }

        emit ArbitrageExecuted(params.tokenOut, params.tokenIn, amountOutV2, amountOutV3, 0);

        require(amountOutV3 >= params.amount + feeAmount, "Insufficient funds to repay loan");

        // Repay loan
        IERC20(params.tokenIn).transfer(address(BALANCER_VAULT), params.amount + feeAmount);

        uint256 profit = amountOutV3 - (params.amount + feeAmount);
        emit ArbitrageExecuted(params.tokenIn, params.tokenOut, params.amount, amountOutV3, profit);
    }

    function getAddresses(IERC20[] memory tokens) internal pure returns (address[] memory) {
        address[] memory addresses = new address[](tokens.length);
        for (uint i = 0; i < tokens.length; i++) {
            addresses[i] = address(tokens[i]);
        }
        return addresses;
    }

    function withdraw(address token, uint256 amount) external onlyOwner {
        if (token == address(0)) {
            payable(owner).transfer(amount);
        } else {
            IERC20(token).transfer(owner, amount);
        }
    }

    receive() external payable {}
}