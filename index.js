import { connect } from 'puppeteer-real-browser';
import fs from 'fs';

async function test() {
    const { browser, page } = await connect({
        headless: false,
        args: [],
        customConfig: {},
        turnstile: true,
        connectOption: {},
        disableXvfb: false,
        ignoreAllFlags: false,
    });

    console.log('Connected to Puppeteer Real Browser');

    await page.goto('https://dexscreener.com/page-1', { waitUntil: "domcontentloaded" });
    console.log('Page loaded');

    // Save WebSocket Debugging URL for Python
    const wsEndpoint = browser.wsEndpoint();
    fs.writeFileSync('browser_endpoint.txt', wsEndpoint);

    // Extract and save the page content
    const pageContent = await page.content();
    fs.writeFileSync('page.html', pageContent);

    console.log('WebSocket saved. You can now run the Python script.');

    // Keep the browser open for Python to attach
    await new Promise(resolve => setTimeout(resolve, 60000)); // Keep open for 60 sec
}

test();
