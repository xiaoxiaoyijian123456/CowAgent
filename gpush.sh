#!/bin/bash
set -e

cd "$(dirname "$0")"

git add ./
git commit -m "updated"
git push origin dev
