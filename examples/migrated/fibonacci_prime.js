const data = require('fs').readFileSync(0, 'utf8').trim().split(/\s+/)

function fibonacci(n) {
  let a = 0n
  let b = 1n
  for (let i = 0; i < n; i += 1) {
    const next = a + b
    a = b
    b = next
  }
  return a
}

function isPrime(n) {
  if (n < 2) return false
  for (let i = 2; i * i <= n; i += 1) {
    if (n % i === 0) return false
  }
  return true
}

if (data.length && data[0] !== '') {
  const n = parseInt(data[0], 10)
  console.log(fibonacci(n).toString())
  console.log(isPrime(n) ? 'prime' : 'not prime')
}
