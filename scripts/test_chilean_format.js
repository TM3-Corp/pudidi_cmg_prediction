#!/usr/bin/env node
/**
 * Test Chilean number formatting function
 */

// Chilean number formatting helper
function formatChilean(number, decimals = 2) {
    const fixed = number.toFixed(decimals);
    const parts = fixed.split('.');
    // Add thousands separator (period)
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    // Join with comma as decimal separator
    return parts.join(',');
}

console.log('='.repeat(60));
console.log('TESTING CHILEAN NUMBER FORMATTING');
console.log('='.repeat(60));
console.log();

// Test cases
const tests = [
    { input: 1234.56, decimals: 2, expected: '1.234,56', desc: 'Standard thousands' },
    { input: 25000, decimals: 0, expected: '25.000', desc: 'Storage value (no decimals)' },
    { input: 2300, decimals: 0, expected: '2.300', desc: 'Generation kW (no decimals)' },
    { input: 72.45, decimals: 2, expected: '72,45', desc: 'Price (2 decimals)' },
    { input: 1500000, decimals: 0, expected: '1.500.000', desc: 'Millions' },
    { input: 123, decimals: 2, expected: '123,00', desc: 'Small number' },
    { input: 0.5, decimals: 2, expected: '0,50', desc: 'Less than 1' },
];

console.log('Test Results:');
console.log('-'.repeat(60));

let passed = 0;
let failed = 0;

tests.forEach((test, i) => {
    const result = formatChilean(test.input, test.decimals);
    const status = result === test.expected ? '✅ PASS' : '❌ FAIL';

    console.log(`${i + 1}. ${test.desc}`);
    console.log(`   Input:    ${test.input} (decimals: ${test.decimals})`);
    console.log(`   Expected: ${test.expected}`);
    console.log(`   Got:      ${result}`);
    console.log(`   ${status}`);
    console.log();

    if (result === test.expected) {
        passed++;
    } else {
        failed++;
    }
});

console.log('='.repeat(60));
console.log(`Summary: ${passed}/${tests.length} tests passed`);
if (failed === 0) {
    console.log('✅ ALL TESTS PASSED!');
} else {
    console.log(`❌ ${failed} test(s) failed`);
}
console.log('='.repeat(60));
