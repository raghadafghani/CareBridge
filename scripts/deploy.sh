#!/usr/bin/env bash
# Deploy CareBridge to Amazon Bedrock AgentCore Runtime.
# Local:  ./scripts/deploy.sh
# GitHub: .github/workflows/deploy.yml runs this on every push to main.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

region="${AWS_REGION:-us-east-1}"
target="${AGENTCORE_TARGET:-default}"

# The Python starter-toolkit binary is also named agentcore and has no --version.
# The workshop CLI is the npm package @aws/agentcore.
if [[ -d "${HOME}/.npm-global/bin" ]]; then
  export PATH="${HOME}/.npm-global/bin:${PATH}"
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required. Install Node.js, then run this script again." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required to package the Python runtime. Install it from https://docs.astral.sh/uv/" >&2
  exit 1
fi

if ! command -v agentcore >/dev/null 2>&1 || ! agentcore --version >/dev/null 2>&1; then
  npm install -g @aws/agentcore
fi

if ! agentcore --version >/dev/null 2>&1; then
  npm_bin="$(npm prefix -g)/bin"
  export PATH="${npm_bin}:${PATH}"
fi

if [[ ! -f agentcore/cdk/package.json ]]; then
  echo "agentcore/cdk is missing. This is the CloudFormation app the AgentCore CLI deploys." >&2
  exit 1
fi

echo "Installing the AgentCore CloudFormation app"
npm install --prefix agentcore/cdk

echo "Building CareBridge for ${region}"
agentcore build --region "$region"

echo "Deploying CareBridge to ${region}"
agentcore deploy --target "$target" --region "$region"

agentcore status --target "$target" --region "$region"
