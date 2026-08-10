"""Example browser canary.

Rename this file to match canary_name (e.g. my-canary.py -> handler "my-canary.handler").
Standard Synthetics browser canary: loads a URL and takes a screenshot.
"""

from aws_synthetics.selenium import synthetics_webdriver as syn_webdriver


def handler(event, context):
    browser = syn_webdriver.Chrome()
    try:
        browser.get("https://example.com")
        browser.get_screenshot()
    finally:
        browser.close()
    return "canary ran successfully"
