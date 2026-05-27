#!/usr/bin/env python3
"""Analyze IAM login page - extract form structure and encryption method."""
import requests, re

s = requests.Session()
r = s.get('https://ycfw.library.hb.cn:8000/cas/login', allow_redirects=True, timeout=15)
html = r.text
print(f"URL: {r.url}")
print(f"Length: {len(html)}")

# Extract all input fields
for m in re.finditer(r'<input[^>]+>', html):
    inp = m.group(0)
    print(f"  INPUT: {inp}")

# Find form action
for m in re.finditer(r'action="([^"]*)"', html):
    print(f"  FORM action: {m.group(1)}")

# Check for encryption keywords
for kw in ['encrypt', 'JSEncrypt', 'RSA', 'publicKey', 'public_key', 'pkcs']:
    if kw.lower() in html.lower():
        idx = html.lower().index(kw.lower())
        print(f"  Found '{kw}' near: {html[max(0,idx-50):idx+100]}")

# Extract password-related JS
print("\n--- Password/encrypt JS ---")
for m in re.finditer(r'<script[^>]*>(.*?)</script>', html, re.DOTALL):
    script = m.group(1)
    if any(w in script for w in ['encrypt', 'password', 'submit', 'login']):
        lines = [l.strip() for l in script.split('\n') if any(w in l.lower() for w in ['encrypt', 'password', 'submit', 'login', 'captcha', 'ajax'])]
        for l in lines[:10]:
            print(f"  {l[:200]}")
