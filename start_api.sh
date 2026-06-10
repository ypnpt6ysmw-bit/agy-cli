#!/bin/bash
cd /Users/arielkurek/.hermes/agy-api
export PATH="/Users/arielkurek/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export HOME="/Users/arielkurek"
export PYTHONUNBUFFERED=1
exec .venv/bin/python -u agy_api.py
