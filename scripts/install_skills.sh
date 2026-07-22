#!/usr/bin/env bash
# Install payagent skills into local agents (wrapper around CLI).
set -euo pipefail
exec payagent skills install --agents "${1:-auto}" --force
