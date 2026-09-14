"""Exercise real Windows argument parsing and native stderr redirection."""
import sys

assert sys.argv[2:] == ['space in path', 'embedded"quote', 'C:\\trailing space\\', '']
sys.stderr.write('\nWARNING: outside Slurm\n' + 'progress\r' * 20000)
sys.stderr.flush()
print('stdout completed')
if sys.argv[1] == 'fail':
    sys.stderr.write('\nfixture failure\n')
    raise SystemExit(7)
