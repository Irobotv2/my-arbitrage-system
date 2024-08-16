// SPDX-License-Identifier: MIT
pragma solidity ^0.7.0;

import "@balancer-labs/v2-interfaces/contracts/vault/IVault.sol";
import "@balancer-labs/v2-interfaces/contracts/vault/IFlashLoanRecipient.sol";
import "@balancer-labs/v2-interfaces/contracts/solidity-utils/openzeppelin/IERC20.sol";
import '@uniswap/v2-core/contracts/interfaces/IUniswapV2Callee.sol';
import '@uniswap/v2-core/contracts/interfaces/IUniswapV2Factory.sol';
import '@uniswap/v2-core/contracts/interfaces/IUniswapV2Pair.sol';
import '@uniswap/v3-core/contracts/interfaces/callback/IUniswapV3FlashCallback.sol';
import '@uniswap/v3-core/contracts/interfaces/IUniswapV3Pool.sol';

contract FlashLoanBundleExecutor is IFlashLoanRecipient, IUniswapV2Callee, IUniswapV3FlashCallback {
    IVault private constant BALANCER_VAULT = IVault(0xBA12222222228d8Ba445958a75a0704d566BF2C8);
    address private constant UNISWAP_V2_FACTORY = 0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f;
    address public owner;

    event FlashLoanInitiated(address[] tokens, uint256[] amounts);
    event FlashLoanCompleted(address[] tokens, uint256[] amounts, uint256[] fees);
    event BalanceCheck(address token, uint256 balance);
    event TransactionExecuted(address targetAddress, bytes callData);
    event TransactionFailed(address targetAddress, bytes callData);
    event EndAmountGreaterThanEstimatedResultAmount(uint256 endAmount, uint256 estimatedResultAmount);

    struct BundleData {
        address token;
        uint256 startAmount;
        uint256 endAmount;
        bytes[] callData;
        address[] to;
    }

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can call this function");
        _;
    }

    function makeFlashLoan(IERC20[] memory tokens, uint256[] memory amounts, bytes memory userData) external onlyOwner {
        address[] memory tokenAddresses = new address[](tokens.length);
        for (uint i = 0; i < tokens.length; i++) {
            tokenAddresses[i] = address(tokens[i]);
        }
        emit FlashLoanInitiated(tokenAddresses, amounts);
        BALANCER_VAULT.flashLoan(this, tokens, amounts, userData);
    }

    function executeBundle(BundleData memory bundle) private returns (uint256 endAmount) {
        for (uint256 i = 0; i < bundle.callData.length; i++) {
            (bool success, ) = bundle.to[i].call(bundle.callData[i]);
            if (success) {
                emit TransactionExecuted(bundle.to[i], bundle.callData[i]);
            } else {
                emit TransactionFailed(bundle.to[i], bundle.callData[i]);
                revert("Transaction failed");
            }
        }

        endAmount = IERC20(bundle.token).balanceOf(address(this));
        require(endAmount > bundle.startAmount, "End amount is not greater than start amount");

        if (endAmount > bundle.endAmount) {
            emit EndAmountGreaterThanEstimatedResultAmount(endAmount, bundle.endAmount);
        }

        return endAmount;
    }

    function receiveFlashLoan(
        IERC20[] memory tokens,
        uint256[] memory amounts,
        uint256[] memory feeAmounts,
        bytes memory userData
    ) external override {
        require(msg.sender == address(BALANCER_VAULT), "Only Balancer Vault can call this function");
        
        logBalances(tokens);

        BundleData memory bundle = abi.decode(userData, (BundleData));
        uint256 endAmount = executeBundle(bundle);

        repayLoan(tokens, amounts, feeAmounts, endAmount);

        emitFlashLoanCompleted(tokens, amounts, feeAmounts);
    }

    function uniswapV2Call(address sender, uint amount0, uint amount1, bytes calldata data) external override {
        require(msg.sender == IUniswapV2Factory(UNISWAP_V2_FACTORY).getPair(IUniswapV2Pair(msg.sender).token0(), IUniswapV2Pair(msg.sender).token1()), "Unauthorized");

        BundleData memory bundle = abi.decode(data, (BundleData));
        uint256 endAmount = executeBundle(bundle);

        uint256 amountOwing = bundle.token == IUniswapV2Pair(msg.sender).token0() ? amount0 : amount1;
        require(endAmount >= amountOwing, "Insufficient funds to repay flash swap");

        IERC20(bundle.token).transfer(msg.sender, amountOwing);
    }

    function uniswapV3FlashCallback(uint256 fee0, uint256 fee1, bytes calldata data) external override {
        BundleData memory bundle = abi.decode(data, (BundleData));
        uint256 endAmount = executeBundle(bundle);

        IUniswapV3Pool pool = IUniswapV3Pool(msg.sender);
        uint256 fee = bundle.token == pool.token0() ? fee0 : fee1;
        uint256 amountOwing = bundle.startAmount + fee;
        require(endAmount >= amountOwing, "Insufficient funds to repay flash swap");

        IERC20(bundle.token).transfer(msg.sender, amountOwing);
    }

    function logBalances(IERC20[] memory tokens) private {
        for (uint256 i = 0; i < tokens.length; i++) {
            uint256 balance = tokens[i].balanceOf(address(this));
            emit BalanceCheck(address(tokens[i]), balance);
        }
    }

    function repayLoan(IERC20[] memory tokens, uint256[] memory amounts, uint256[] memory feeAmounts, uint256 endAmount) private {
        for (uint256 i = 0; i < tokens.length; i++) {
            uint256 totalRepayment = amounts[i] + feeAmounts[i];
            require(endAmount >= totalRepayment, "Insufficient funds to repay flash loan");
            tokens[i].transfer(address(BALANCER_VAULT), totalRepayment);
        }
    }

    function emitFlashLoanCompleted(IERC20[] memory tokens, uint256[] memory amounts, uint256[] memory feeAmounts) private {
        address[] memory tokenAddresses = new address[](tokens.length);
        for (uint i = 0; i < tokens.length; i++) {
            tokenAddresses[i] = address(tokens[i]);
        }
        emit FlashLoanCompleted(tokenAddresses, amounts, feeAmounts);
    }

    receive() external payable {}

    function withdraw(address token, uint256 amount) external onlyOwner {
        if (token == address(0)) {
            payable(owner).transfer(amount);
        } else {
            IERC20(token).transfer(owner, amount);
        }
    }
}