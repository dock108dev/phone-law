#!/usr/bin/env bash
set -euo pipefail

# Official actionlint release, checksum-pinned independently of the download.
version=1.7.12
case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) platform=linux_amd64; checksum=8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8 ;;
  Linux-aarch64) platform=linux_arm64; checksum=325e971b6ba9bfa504672e29be93c24981eeb1c07576d730e9f7c8805afff0c6 ;;
  Darwin-arm64) platform=darwin_arm64; checksum=aba9ced2dee8d27fecca3dc7feb1a7f9a52caefa1eb46f3271ea66b6e0e6953f ;;
  Darwin-x86_64) platform=darwin_amd64; checksum=5b44c3bc2255115c9b69e30efc0fecdf498fdb63c5d58e17084fd5f16324c644 ;;
  *) echo "Unsupported actionlint platform" >&2; exit 1 ;;
esac
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
archive="$work/actionlint.tar.gz"
curl --fail --silent --show-error --location --retry 3 --connect-timeout 10 --max-time 60 \
  "https://github.com/rhysd/actionlint/releases/download/v${version}/actionlint_${version}_${platform}.tar.gz" \
  --output "$archive"
printf '%s  %s\n' "$checksum" "$archive" | shasum -a 256 --check
tar -xzf "$archive" -C "$work" actionlint
# ShellCheck is used automatically where installed (including GitHub's Ubuntu image).
"$work/actionlint" -color .github/workflows/*.yml
