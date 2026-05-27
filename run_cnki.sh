#!/bin/bash
# Wrapper to run the Playwright CNKI login + fetch script
cd /root/news-monitor
python3 playwright_lib_login.py "$@"
