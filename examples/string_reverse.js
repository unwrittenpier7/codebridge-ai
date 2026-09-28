const input = require('fs').readFileSync(0, 'utf8').split('\n')[0]

function reverse(text) {
  return text.split('').reverse().join('')
}

console.log(reverse(input.trim()))
